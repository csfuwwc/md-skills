import json
import hashlib
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = pathlib.Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import upload_attachments
from upload_attachments import build_upload_command


class UploadSecurityTests(unittest.TestCase):
    def test_duplicate_stems_use_distinct_token_directories_and_repeated_file_flags(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as upload_root:
            first = pathlib.Path(source_dir) / "box_1.png"
            second = pathlib.Path(source_dir) / "box_2.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            job = {"target_table_id": "tbl", "target_record_id": "rec", "field_name": "Images", "files": [
                {"file_token": "box_1", "name": "same.webp", "output_path": str(first)},
                {"file_token": "box_2", "name": "same.jpg", "output_path": str(second)},
            ]}

            argv, _ = build_upload_command("app_target", job, upload_root)

            staged = [argv[index + 1] for index, item in enumerate(argv) if item == "--file"]
            self.assertEqual(staged, ["./box_1/same.png", "./box_2/same.png"])

    def test_rejects_token_directory_symlink_escape(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as upload_root, tempfile.TemporaryDirectory() as outside:
            source = pathlib.Path(source_dir) / "box_1.png"
            source.write_bytes(b"png")
            os.symlink(outside, pathlib.Path(upload_root) / "box_1")
            job = {"target_table_id": "tbl", "target_record_id": "rec", "field_name": "Images",
                   "files": [{"file_token": "box_1", "name": "one.webp", "output_path": str(source)}]}
            with self.assertRaisesRegex(ValueError, "symlink"):
                build_upload_command("app_target", job, upload_root)
            self.assertEqual(list(pathlib.Path(outside).iterdir()), [])

    def test_rejects_stale_staged_file_with_different_content(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as upload_root:
            source = pathlib.Path(source_dir) / "box_1.png"
            source.write_bytes(b"current")
            staged_dir = pathlib.Path(upload_root) / "box_1"
            staged_dir.mkdir()
            (staged_dir / "one.png").write_bytes(b"stale")
            job = {"target_table_id": "tbl", "target_record_id": "rec", "field_name": "Images",
                   "files": [{"file_token": "box_1", "name": "one.webp", "output_path": str(source)}]}

            with self.assertRaisesRegex(ValueError, "staged attachment"):
                build_upload_command("app_target", job, upload_root)

    def test_rejects_source_file_that_does_not_match_manifest_hash(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as upload_root:
            source = pathlib.Path(source_dir) / "box_1.png"
            source.write_bytes(b"tampered")
            expected = hashlib.sha256(b"expected").hexdigest()
            job = {"target_table_id": "tbl", "target_record_id": "rec", "field_name": "Images",
                   "files": [{"file_token": "box_1", "name": "one.webp", "output_path": str(source),
                              "sha256": expected}]}

            with self.assertRaisesRegex(ValueError, "checksum"):
                build_upload_command("app_target", job, upload_root)

    def test_uploader_stops_after_first_failed_job(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as upload_root:
            first = pathlib.Path(source_dir) / "box_1.png"
            second = pathlib.Path(source_dir) / "box_2.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            jobs = [
                {"table_name": "T", "target_table_id": "tbl", "target_record_id": "rec1", "field_name": "Images",
                 "files": [{"file_token": "box_1", "name": "one.webp", "output_path": str(first)}]},
                {"table_name": "T", "target_table_id": "tbl", "target_record_id": "rec2", "field_name": "Images",
                 "files": [{"file_token": "box_2", "name": "two.webp", "output_path": str(second)}]},
            ]
            plan = pathlib.Path(source_dir) / "plan.json"
            plan.write_text(json.dumps(jobs))
            argv = ["upload_attachments.py", "--target-token", "app_target", "--plan", str(plan),
                    "--upload-root", upload_root]
            failed = mock.Mock(returncode=1, stdout="", stderr="temporary failure")

            with mock.patch.object(sys, "argv", argv), mock.patch.object(upload_attachments.subprocess, "run", return_value=failed) as run, \
                    mock.patch("builtins.print"):
                with self.assertRaises(SystemExit):
                    upload_attachments.main()

            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
