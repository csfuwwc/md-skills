import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = pathlib.Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import replica
from replica import RunLedger, StateError, cleanup_ephemeral, hydrate_attachments, probe_upload_capability


class ReplicaRunnerTests(unittest.TestCase):
    def test_ledger_enforces_order_and_private_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = RunLedger.create(directory, source="app_source", target="app_target")
            self.assertEqual(stat.S_IMODE(os.stat(ledger.path).st_mode), 0o600)
            ledger.advance("PROBED", {"official_read": True})
            with self.assertRaises(StateError):
                ledger.advance("PLANNED", {})
            reloaded = RunLedger.load(directory)
            self.assertEqual(reloaded.data["state"], "PROBED")
            self.assertNotIn("access_token", json.dumps(reloaded.data))

    def test_cleanup_deletes_only_registered_paths_inside_run_directory(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            ledger = RunLedger.create(directory, source="app_source", target="app_target")
            cache = pathlib.Path(directory) / "decrypted" / "one.png"
            cache.parent.mkdir()
            cache.write_bytes(b"x")
            ledger.register_ephemeral(cache)
            cleanup_ephemeral(ledger)
            self.assertFalse(cache.exists())
            foreign = pathlib.Path(outside) / "keep.txt"
            foreign.write_text("keep")
            with self.assertRaises(ValueError):
                ledger.register_ephemeral(foreign)
            self.assertTrue(foreign.exists())

    def test_probe_requires_explicit_multi_file_append_contract(self):
        old_help = "--file string  local file path"
        new_help = "--file stringArray  repeat --file to append multiple files into the same attachment cell"
        current_help = "--file stringArray local file path; repeat to append multiple attachments in one cell; max 50 files"
        self.assertFalse(probe_upload_capability(old_help)["multi_file_append"])
        self.assertTrue(probe_upload_capability(new_help)["multi_file_append"])
        self.assertTrue(probe_upload_capability(current_help)["multi_file_append"])

    def test_hydrate_attachments_adds_only_safe_local_fidelity_metadata(self):
        source = {"tables": [{"records": [{"attachments": {"Images": [{"file_token": "box_1", "name": "one.webp"}]}}]}]}
        download = {"files": [{"file_token": "box_1", "output_path": "/tmp/box_1.png", "format": "png",
                               "sha256": "a" * 64, "width": 720, "height": 640, "plain_bytes": 123}]}
        hydrated = hydrate_attachments(source, download)
        item = hydrated["tables"][0]["records"][0]["attachments"]["Images"][0]
        self.assertEqual(item["output_path"], "/tmp/box_1.png")
        self.assertEqual(item["format"], "png")
        self.assertNotIn("url", json.dumps(hydrated))

    def test_hydrate_attachments_rejects_secret_fields_and_missing_files(self):
        source = {"tables": [{"records": [{"attachments": {"Images": [{"file_token": "box_1"}]}}]}]}
        with self.assertRaisesRegex(ValueError, "secret"):
            hydrate_attachments(source, {"files": [{"file_token": "box_1", "url": "signed"}]})
        with self.assertRaisesRegex(ValueError, "missing decrypted attachment"):
            hydrate_attachments(source, {"files": []})

    def test_refresh_attachment_plan_after_interruption_keeps_only_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = RunLedger.create(directory, source="app_source", target="app_target")
            first = pathlib.Path(directory) / "box_1.png"
            second = pathlib.Path(directory) / "box_2.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            source = {"tables": [{
                "name": "Prompts",
                "target_table_id": "tbl_target",
                "records": [{
                    "target_record_id": "rec_target",
                    "attachments": {"Images": [
                        {"file_token": "box_1", "name": "same.webp", "output_path": str(first)},
                        {"file_token": "box_2", "name": "same.jpg", "output_path": str(second)},
                    ]},
                }],
            }]}
            target = {"manifest_version": 1, "role": "target", "base_token": "app_target", "tables": [{
                "name": "Prompts",
                "table_id": "tbl_target",
                "records": [{
                    "record_id": "rec_target",
                    "attachments": {"Images": [{"name": "same.png"}]},
                }],
            }]}
            source_path = pathlib.Path(directory) / "source-hydrated-manifest.json"
            source_path.write_text(json.dumps(source))
            ledger.data["artifacts"]["attachment_source_manifest"] = source_path.name
            ledger.save()

            plan = replica.refresh_attachment_plan(ledger, target)

            self.assertEqual([item["file_token"] for item in plan[0]["files"]], ["box_1"])
            plan_path = pathlib.Path(directory) / "attachment-plan.json"
            self.assertEqual(stat.S_IMODE(os.stat(plan_path).st_mode), 0o600)

    def test_refresh_attachment_plan_rejects_source_file_outside_run_directory(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            ledger = RunLedger.create(directory, source="app_source", target="app_target")
            source_file = pathlib.Path(outside) / "box_1.png"
            source_file.write_bytes(b"png")
            source = {"tables": [{
                "name": "Prompts", "target_table_id": "tbl_target",
                "records": [{"target_record_id": "rec_target", "attachments": {
                    "Images": [{"file_token": "box_1", "name": "one.webp", "output_path": str(source_file)}]
                }}],
            }]}
            target = {"tables": [{
                "name": "Prompts", "table_id": "tbl_target",
                "records": [{"record_id": "rec_target", "attachments": {"Images": []}}],
            }]}
            source_path = pathlib.Path(directory) / "source-hydrated-manifest.json"
            replica.write_private(str(source_path), source)
            ledger.data["artifacts"]["attachment_source_manifest"] = source_path.name
            ledger.save()

            with self.assertRaisesRegex(ValueError, "run directory"):
                replica.refresh_attachment_plan(ledger, target)

    def test_retry_attachment_phase_refreshes_plan_from_fresh_target_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = RunLedger.create(directory, source="app_source", target="app_target")
            ledger.advance("PROBED", {"multi_file_append": True})
            ledger.advance("SNAPSHOTTED", {})
            ledger.advance("PLANNED", {})
            ledger.advance("STRUCTURE_WRITTEN", {})
            first = pathlib.Path(directory) / "box_1.png"
            second = pathlib.Path(directory) / "box_2.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            source = {"tables": [{
                "name": "Prompts", "target_table_id": "tbl_target", "fields": [], "views": [],
                "records": [{"target_record_id": "rec_target", "values": {}, "attachments": {"Images": [
                    {"file_token": "box_1", "name": "one.webp", "output_path": str(first)},
                    {"file_token": "box_2", "name": "two.webp", "output_path": str(second)},
                ]}}],
            }]}
            target = {"manifest_version": 1, "role": "target", "base_token": "app_target", "tables": [{
                "name": "Prompts", "table_id": "tbl_target", "fields": [], "views": [],
                "records": [{"record_id": "rec_target", "values": {},
                             "attachments": {"Images": [{"name": "one.png"}]}}],
            }]}
            source_path = pathlib.Path(directory) / "source-manifest.json"
            hydrated_path = pathlib.Path(directory) / "source-hydrated-manifest.json"
            target_path = pathlib.Path(directory) / "target-after-interruption.json"
            replica.write_private(str(source_path), source)
            replica.write_private(str(hydrated_path), source)
            replica.write_private(str(target_path), target)
            ledger.data["artifacts"].update({
                "source_manifest": source_path.name,
                "attachment_source_manifest": hydrated_path.name,
                "attachment_plan": "attachment-plan.json",
            })
            ledger.save()
            ledger.advance("RECORDS_VERIFIED", {})
            upload_root = pathlib.Path(directory) / "upload-ready"
            argv = [
                "replica.py", "apply", "--run-dir", directory, "--phase", "attachments",
                "--evidence", str(target_path), "--authorized-target", "app_target",
                "--upload-root", str(upload_root),
            ]

            with mock.patch.object(sys, "argv", argv), mock.patch.object(replica.subprocess, "run") as run, \
                    mock.patch("builtins.print"):
                replica._main()

            plan = json.loads((pathlib.Path(directory) / "attachment-plan.json").read_text())
            self.assertEqual([item["file_token"] for item in plan[0]["files"]], ["box_2"])
            run.assert_called_once()

    def test_apply_rejects_evidence_from_another_target(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = RunLedger.create(directory, source="app_source", target="app_target")
            ledger.advance("PROBED", {"multi_file_append": True})
            ledger.advance("SNAPSHOTTED", {})
            ledger.advance("PLANNED", {})
            source = {"manifest_version": 1, "role": "source", "base_token": "app_source", "tables": []}
            evidence = {"manifest_version": 1, "role": "target", "base_token": "app_other", "tables": []}
            source_path = pathlib.Path(directory) / "source-manifest.json"
            evidence_path = pathlib.Path(directory) / "target-evidence.json"
            replica.write_private(str(source_path), source)
            replica.write_private(str(evidence_path), evidence)
            ledger.data["artifacts"]["source_manifest"] = source_path.name
            ledger.save()
            argv = [
                "replica.py", "apply", "--run-dir", directory, "--phase", "structure",
                "--evidence", str(evidence_path), "--authorized-target", "app_target",
            ]

            with mock.patch.object(sys, "argv", argv), mock.patch("builtins.print"):
                with self.assertRaises(PermissionError):
                    replica._main()

            self.assertEqual(RunLedger.load(directory).data["state"], "PLANNED")


if __name__ == "__main__":
    unittest.main()
