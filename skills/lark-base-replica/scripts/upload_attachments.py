#!/usr/bin/env python3
import argparse
import errno
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess


TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_upload_command(target_token, job, upload_root):
    files = job.get("files", [])
    if not 1 <= len(files) <= 50:
        raise ValueError("one attachment cell must contain 1..50 files")
    root = pathlib.Path(upload_root)
    root.mkdir(parents=True, exist_ok=True)
    argv = [
        "lark-cli", "base", "+record-upload-attachment", "--as", "user",
        "--base-token", target_token,
        "--table-id", job["target_table_id"],
        "--record-id", job["target_record_id"],
        "--field-id", job["field_name"],
        "--format", "json",
    ]
    for item in files:
        token = item["file_token"]
        if not TOKEN_PATTERN.fullmatch(token):
            raise ValueError("unsafe file token")
        source = pathlib.Path(item["output_path"])
        if source.is_symlink() or not source.is_file():
            raise ValueError("attachment source must be a regular non-symlink file")
        source_digest = _sha256(source)
        if item.get("sha256") and source_digest != item["sha256"].lower():
            raise ValueError("attachment source checksum does not match the manifest")
        extension = source.suffix.lower()
        display_name = pathlib.Path(item.get("name") or token).stem + extension
        directory = root / token
        if directory.is_symlink():
            raise ValueError("attachment staging directory must not be a symlink")
        directory.mkdir(exist_ok=True)
        if root.resolve() not in directory.resolve().parents:
            raise ValueError("attachment staging directory escaped upload root")
        destination = directory / display_name
        if destination.is_symlink():
            destination.unlink()
        if destination.exists():
            if _sha256(destination) != source_digest:
                raise ValueError("staged attachment content differs from the current source")
        else:
            try:
                os.link(source, destination)
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
                shutil.copy2(source, destination)
        relative = "./" + destination.relative_to(root).as_posix()
        argv.extend(["--file", relative])
    return argv, str(root)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-token", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--upload-root", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with open(args.plan, encoding="utf-8") as handle:
        jobs = json.load(handle)
    failures = []
    uploaded = 0
    for job in jobs:
        argv, cwd = build_upload_command(args.target_token, job, args.upload_root)
        if args.dry_run:
            print(json.dumps({"cwd": cwd, "argv": argv}, ensure_ascii=False))
            continue
        result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True)
        raw = result.stdout.strip() or result.stderr.strip()
        if result.returncode == 0:
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {}
            if payload.get("ok"):
                uploaded += len(job["files"])
                continue
        failures.append({
            "table_name": job.get("table_name"),
            "target_record_id": job["target_record_id"],
            "field_name": job["field_name"],
            "error": raw[-2000:],
        })
        break
    print(json.dumps({"uploaded": uploaded, "failures": failures}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
