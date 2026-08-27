#!/usr/bin/env python3
import argparse
import collections
import json
import os
import pathlib


def _stem(name):
    return pathlib.Path(name or "").stem


def _tables(manifest):
    return {table["name"]: table for table in manifest.get("tables", [])}


def _records(table, key):
    return {record[key]: record for record in table.get("records", [])}


def compare_replica(source, target):
    source_tables = _tables(source)
    target_tables = _tables(target)
    structure_mismatches = []
    value_mismatches = []
    attachment_mismatches = []
    verified_records = 0
    verified_cells = 0

    if source_tables.keys() != target_tables.keys():
        structure_mismatches.append({
            "kind": "tables",
            "source": sorted(source_tables),
            "target": sorted(target_tables),
        })

    for name in sorted(source_tables.keys() & target_tables.keys()):
        source_table = source_tables[name]
        target_table = target_tables[name]
        for kind in ("fields", "views"):
            if source_table.get(kind, []) != target_table.get(kind, []):
                structure_mismatches.append({"kind": kind, "table": name})

        target_records = _records(target_table, "record_id")
        expected_target_ids = {record.get("target_record_id") for record in source_table.get("records", [])}
        if expected_target_ids != set(target_records):
            value_mismatches.append({
                "table": name,
                "kind": "record_set",
                "source": sorted(str(item) for item in expected_target_ids),
                "target": sorted(target_records),
            })
        for source_record in source_table.get("records", []):
            target_id = source_record.get("target_record_id")
            target_record = target_records.get(target_id)
            if target_record is None:
                value_mismatches.append({"table": name, "record_id": target_id, "kind": "missing_record"})
                continue
            verified_records += 1
            source_values = source_record.get("values", {})
            target_values = target_record.get("values", {})
            if source_values.keys() != target_values.keys():
                value_mismatches.append({
                    "table": name,
                    "record_id": target_id,
                    "kind": "value_fields",
                    "source": sorted(source_values),
                    "target": sorted(target_values),
                })
            for field, expected in source_values.items():
                verified_cells += 1
                if target_values.get(field) != expected:
                    value_mismatches.append({"table": name, "record_id": target_id, "field": field})
            source_attachments = source_record.get("attachments", {})
            target_attachments = target_record.get("attachments", {})
            for field in sorted(source_attachments.keys() | target_attachments.keys()):
                source_files = source_attachments.get(field, [])
                target_files = target_attachments.get(field, [])
                if collections.Counter(_stem(item.get("name")) for item in source_files) != collections.Counter(
                    _stem(item.get("name")) for item in target_files
                ):
                    attachment_mismatches.append({"table": name, "record_id": target_id, "field": field})

    return {
        "verified_records": verified_records,
        "verified_cells": verified_cells,
        "structure_mismatches": structure_mismatches,
        "value_mismatches": value_mismatches,
        "attachment_mismatches": attachment_mismatches,
    }


def plan_missing_attachments(source, target):
    source_tables = _tables(source)
    target_tables = _tables(target)
    plan = []
    for table_name, source_table in source_tables.items():
        target_table = target_tables.get(table_name)
        if target_table is None:
            raise ValueError(f"target table missing: {table_name}")
        target_records = _records(target_table, "record_id")
        for source_record in source_table.get("records", []):
            target_id = source_record.get("target_record_id")
            target_record = target_records.get(target_id)
            if target_record is None:
                raise ValueError(f"target record missing: {table_name}/{target_id}")
            source_attachments = source_record.get("attachments", {})
            target_attachments = target_record.get("attachments", {})
            for field_name in target_attachments.keys() - source_attachments.keys():
                target_files = target_attachments[field_name]
                if target_files:
                    raise ValueError(
                        f"target attachment not present in source: {table_name}/{target_id}/{field_name}/{target_files[0].get('name')}"
                    )
            for field_name, source_files in source_attachments.items():
                target_files = target_attachments.get(field_name, [])
                remaining = collections.Counter(_stem(item.get("name")) for item in source_files)
                for target_file in target_files:
                    stem = _stem(target_file.get("name"))
                    if remaining[stem] <= 0:
                        raise ValueError(
                            f"target attachment not present in source: {table_name}/{target_id}/{field_name}/{target_file.get('name')}"
                        )
                    remaining[stem] -= 1
                missing = []
                for source_file in source_files:
                    stem = _stem(source_file.get("name"))
                    if remaining[stem] > 0:
                        missing.append(source_file)
                        remaining[stem] -= 1
                if missing:
                    plan.append({
                        "table_name": table_name,
                        "target_table_id": source_table.get("target_table_id") or target_table.get("table_id"),
                        "target_record_id": target_id,
                        "field_name": field_name,
                        "files": missing,
                    })
    return plan


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _write_private(path, payload):
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    compare = subparsers.add_parser("compare")
    compare.add_argument("source")
    compare.add_argument("target")
    plan = subparsers.add_parser("plan-attachments")
    plan.add_argument("source")
    plan.add_argument("target")
    plan.add_argument("--output", required=True)
    args = parser.parse_args()
    source = _load(args.source)
    target = _load(args.target)
    if args.command == "compare":
        result = compare_replica(source, target)
        print(json.dumps(result, ensure_ascii=False))
        if any(result[key] for key in ("structure_mismatches", "value_mismatches", "attachment_mismatches")):
            raise SystemExit(1)
    else:
        result = plan_missing_attachments(source, target)
        _write_private(args.output, result)
        print(json.dumps({"cells": len(result), "files": sum(len(job["files"]) for job in result)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
