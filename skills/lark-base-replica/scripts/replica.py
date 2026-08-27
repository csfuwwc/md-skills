#!/usr/bin/env python3
import argparse
import copy
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import uuid

from capture_manifest import capture_stable, write_private
from replica_manifest import compare_replica, plan_missing_attachments


STATES = (
    "NEW",
    "PROBED",
    "SNAPSHOTTED",
    "PLANNED",
    "STRUCTURE_WRITTEN",
    "RECORDS_VERIFIED",
    "ATTACHMENTS_VERIFIED",
    "COMPLETE",
)


class StateError(RuntimeError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class RunLedger:
    def __init__(self, directory, data):
        self.directory = pathlib.Path(directory).resolve()
        self.path = self.directory / "run.json"
        self.data = data

    @classmethod
    def create(cls, directory, source, target):
        root = pathlib.Path(directory).resolve()
        root.mkdir(parents=True, exist_ok=True)
        ledger = cls(root, {
            "version": 1,
            "run_id": str(uuid.uuid4()),
            "source": source,
            "target": target,
            "state": "NEW",
            "artifacts": {},
            "ephemeral": [],
            "events": [{"at": _now(), "state": "NEW"}],
        })
        if ledger.path.exists():
            raise FileExistsError(str(ledger.path))
        ledger.save()
        return ledger

    @classmethod
    def load(cls, directory):
        root = pathlib.Path(directory).resolve()
        with open(root / "run.json", encoding="utf-8") as handle:
            return cls(root, json.load(handle))

    def save(self):
        write_private(str(self.path), self.data)

    def advance(self, state, evidence):
        current = STATES.index(self.data["state"])
        requested = STATES.index(state)
        if requested != current + 1:
            raise StateError(f"invalid transition: {self.data['state']} -> {state}")
        self.data["state"] = state
        self.data["events"].append({"at": _now(), "state": state, "evidence": evidence})
        self.save()

    def register_ephemeral(self, path):
        candidate = pathlib.Path(path).resolve()
        if candidate == self.directory or self.directory not in candidate.parents:
            raise ValueError("ephemeral path must be inside the run directory")
        if candidate == self.path:
            raise ValueError("run ledger cannot be ephemeral")
        relative = candidate.relative_to(self.directory).as_posix()
        if relative not in self.data["ephemeral"]:
            self.data["ephemeral"].append(relative)
            self.save()


def cleanup_ephemeral(ledger):
    paths = sorted((ledger.directory / item for item in ledger.data.get("ephemeral", [])), key=lambda item: len(item.parts), reverse=True)
    for candidate in paths:
        resolved = candidate.resolve()
        if resolved == ledger.directory or ledger.directory not in resolved.parents:
            raise ValueError("refusing cleanup outside run directory")
        if resolved.is_dir():
            shutil.rmtree(resolved)
        elif resolved.exists() or resolved.is_symlink():
            resolved.unlink()
    ledger.data["ephemeral"] = []
    ledger.data["cleaned_at"] = _now()
    ledger.save()


def probe_upload_capability(help_text):
    normalized = " ".join(help_text.lower().split())
    same_cell = "same attachment cell" in normalized or "one cell" in normalized
    supported = ("--file stringarray" in normalized and "repeat" in normalized and
                 "append" in normalized and "multiple" in normalized and same_cell)
    return {"multi_file_append": supported}


def hydrate_attachments(source, download_manifest):
    forbidden = {"url", "secret", "nonce", "access_token", "cookie"}

    def check_secrets(value):
        if isinstance(value, dict):
            found = forbidden & set(value)
            if found:
                raise ValueError(f"secret fields are forbidden: {sorted(found)}")
            for item in value.values():
                check_secrets(item)
        elif isinstance(value, list):
            for item in value:
                check_secrets(item)

    check_secrets(download_manifest)
    if download_manifest.get("failures"):
        raise ValueError("attachment download manifest contains failures")
    safe_keys = ("output_path", "format", "sha256", "width", "height", "plain_bytes")
    by_token = {}
    for item in download_manifest.get("files", []):
        token = item.get("file_token")
        if not token or token in by_token:
            raise ValueError("attachment download manifest has a missing or duplicate file token")
        by_token[token] = item
    hydrated = copy.deepcopy(source)
    for table in hydrated.get("tables", []):
        for record in table.get("records", []):
            for attachments in record.get("attachments", {}).values():
                for attachment in attachments:
                    if attachment.get("output_path"):
                        continue
                    token = attachment.get("file_token")
                    local = by_token.get(token)
                    if not local or not local.get("output_path"):
                        raise ValueError(f"missing decrypted attachment: {token}")
                    attachment.update({key: local[key] for key in safe_keys if local.get(key) is not None})
    return hydrated


def refresh_attachment_plan(ledger, target):
    source_name = ledger.data["artifacts"].get("attachment_source_manifest")
    if not source_name:
        raise StateError("hydrated attachment source manifest is missing")
    source = _load(ledger.directory / source_name)
    for table in source.get("tables", []):
        for record in table.get("records", []):
            for attachments in record.get("attachments", {}).values():
                for attachment in attachments:
                    raw_path = attachment.get("output_path")
                    if not raw_path:
                        raise ValueError("attachment source file is missing")
                    candidate = pathlib.Path(raw_path)
                    if candidate.is_symlink():
                        raise ValueError("attachment source file must not be a symlink")
                    resolved = candidate.resolve()
                    if resolved == ledger.directory or ledger.directory not in resolved.parents:
                        raise ValueError("attachment source file must be inside the run directory")
                    if not resolved.is_file():
                        raise ValueError("attachment source must be a regular file")
    plan = plan_missing_attachments(source, target)
    plan_path = ledger.directory / "attachment-plan.json"
    write_private(str(plan_path), plan)
    ledger.data["artifacts"]["attachment_plan"] = plan_path.name
    ledger.data["events"].append({
        "at": _now(),
        "event": "ATTACHMENT_PLAN_REFRESHED",
        "cells": len(plan),
        "files": sum(len(job["files"]) for job in plan),
    })
    ledger.save()
    return plan


def _help(command):
    result = subprocess.run(["lark-cli", "base", command, "--help"], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(f"cannot probe {command}")
    return result.stdout + result.stderr


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _zero(report, domains):
    return all(not report[name] for name in domains)


def _validate_target_evidence(ledger, manifest):
    if manifest.get("manifest_version") != 1:
        raise ValueError("unsupported target evidence manifest version")
    if manifest.get("role") != "target":
        raise ValueError("evidence manifest must have role=target")
    if manifest.get("base_token") != ledger.data["target"]:
        raise PermissionError("evidence manifest does not belong to the authorized target")


def _main():
    parser = argparse.ArgumentParser(description="Resumable Lark Base replica coordinator")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--run-dir", required=True)
    init.add_argument("--source", required=True)
    init.add_argument("--target", required=True)
    for name in ("probe", "snapshot", "plan", "verify", "cleanup"):
        command = sub.add_parser(name)
        command.add_argument("--run-dir", required=True)
        if name == "snapshot":
            command.add_argument("--record-map")
        if name == "cleanup":
            command.add_argument("--confirmed", action="store_true")
    apply = sub.add_parser("apply")
    apply.add_argument("--run-dir", required=True)
    apply.add_argument("--phase", choices=("structure", "records", "attachments"), required=True)
    apply.add_argument("--evidence")
    apply.add_argument("--authorized-target")
    apply.add_argument("--upload-root")
    apply.add_argument("--attachment-manifest")
    apply.add_argument("--ephemeral-path", action="append", default=[])
    args = parser.parse_args()

    if args.command == "init":
        ledger = RunLedger.create(args.run_dir, args.source, args.target)
        print(json.dumps({"run_id": ledger.data["run_id"], "state": ledger.data["state"]}))
        return
    ledger = RunLedger.load(args.run_dir)
    if args.command == "probe":
        if ledger.data["state"] != "NEW":
            raise StateError("probe requires NEW")
        read_commands = ("+table-list", "+field-list", "+view-list", "+record-list")
        official_read = all("Risk: read" in _help(command) for command in read_commands)
        upload = probe_upload_capability(_help("+record-upload-attachment"))
        ledger.advance("PROBED", {"official_read": official_read, **upload})
    elif args.command == "snapshot":
        if ledger.data["state"] != "PROBED":
            raise StateError("snapshot requires PROBED")
        record_map = _load(args.record_map) if args.record_map else None
        source_path = ledger.directory / "source-manifest.json"
        target_path = ledger.directory / "target-manifest.json"
        write_private(str(source_path), capture_stable(ledger.data["source"], role="source", record_map=record_map))
        write_private(str(target_path), capture_stable(ledger.data["target"], role="target"))
        ledger.data["artifacts"].update({"source_manifest": source_path.name, "target_manifest": target_path.name})
        ledger.advance("SNAPSHOTTED", {"source": source_path.name, "target": target_path.name})
    elif args.command == "plan":
        if ledger.data["state"] != "SNAPSHOTTED":
            raise StateError("plan requires SNAPSHOTTED")
        source = _load(ledger.directory / ledger.data["artifacts"]["source_manifest"])
        target = _load(ledger.directory / ledger.data["artifacts"]["target_manifest"])
        report = compare_replica(source, target)
        plan_path = ledger.directory / "replication-plan.json"
        write_private(str(plan_path), {"comparison": report, "next": "write structure, then re-read target"})
        ledger.data["artifacts"]["plan"] = plan_path.name
        ledger.advance("PLANNED", {"plan": plan_path.name})
    elif args.command == "apply":
        if not args.evidence:
            raise ValueError("--evidence is required")
        if args.authorized_target != ledger.data["target"]:
            raise PermissionError("--authorized-target must exactly match the target token")
        source = _load(ledger.directory / ledger.data["artifacts"]["source_manifest"])
        target = _load(args.evidence)
        _validate_target_evidence(ledger, target)
        report = compare_replica(source, target)
        if args.phase == "structure":
            if ledger.data["state"] != "PLANNED" or not _zero(report, ("structure_mismatches",)):
                raise StateError("structure evidence has mismatches or state is invalid")
            ledger.advance("STRUCTURE_WRITTEN", {"evidence": args.evidence})
        elif args.phase == "records":
            if ledger.data["state"] != "STRUCTURE_WRITTEN" or not _zero(report, ("structure_mismatches", "value_mismatches")):
                raise StateError("record evidence has mismatches or state is invalid")
            downloads = _load(args.attachment_manifest) if args.attachment_manifest else {"files": []}
            source = hydrate_attachments(source, downloads)
            hydrated_path = ledger.directory / "source-hydrated-manifest.json"
            write_private(str(hydrated_path), source)
            ledger.data["artifacts"]["attachment_source_manifest"] = hydrated_path.name
            upload_plan = refresh_attachment_plan(ledger, target)
            ledger.advance("RECORDS_VERIFIED", {"evidence": args.evidence, "attachment_cells": len(upload_plan)})
        else:
            if ledger.data["state"] != "RECORDS_VERIFIED":
                raise StateError("attachment apply requires RECORDS_VERIFIED")
            probe = ledger.data["events"][1].get("evidence", {})
            if not probe.get("multi_file_append"):
                raise StateError("CLI does not guarantee multi-file append semantics")
            if not args.upload_root:
                raise ValueError("--upload-root is required")
            refresh_attachment_plan(ledger, target)
            ledger.register_ephemeral(args.upload_root)
            for path in args.ephemeral_path:
                ledger.register_ephemeral(path)
            command = [sys.executable, str(pathlib.Path(__file__).with_name("upload_attachments.py")),
                       "--target-token", ledger.data["target"], "--plan", str(ledger.directory / ledger.data["artifacts"]["attachment_plan"]),
                       "--upload-root", args.upload_root]
            subprocess.run(command, check=True)
            ledger.data["events"].append({"at": _now(), "event": "ATTACHMENTS_APPLIED"})
            ledger.save()
    elif args.command == "verify":
        if ledger.data["state"] != "RECORDS_VERIFIED":
            raise StateError("verify requires RECORDS_VERIFIED")
        source = _load(ledger.directory / ledger.data["artifacts"]["source_manifest"])
        target = capture_stable(ledger.data["target"], role="target")
        final_path = ledger.directory / "target-final-manifest.json"
        write_private(str(final_path), target)
        report = compare_replica(source, target)
        report_path = ledger.directory / "final-report.json"
        write_private(str(report_path), report)
        if not _zero(report, ("structure_mismatches", "value_mismatches", "attachment_mismatches")):
            raise StateError("final verification found mismatches")
        ledger.data["artifacts"].update({"target_final_manifest": final_path.name, "final_report": report_path.name})
        ledger.advance("ATTACHMENTS_VERIFIED", {"report": report_path.name})
        ledger.advance("COMPLETE", {"report": report_path.name})
    else:
        if ledger.data["state"] != "COMPLETE" or not args.confirmed:
            raise StateError("cleanup requires COMPLETE and --confirmed")
        cleanup_ephemeral(ledger)
    print(json.dumps({"run_id": ledger.data["run_id"], "state": ledger.data["state"]}))


if __name__ == "__main__":
    _main()
