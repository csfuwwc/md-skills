#!/usr/bin/env python3
import argparse
import copy
import datetime
import hashlib
import json
import os
import subprocess


class SourceChanged(RuntimeError):
    pass


VIEW_CONFIG_COMMANDS = (
    "+view-get-filter",
    "+view-get-sort",
    "+view-get-group",
    "+view-get-visible-fields",
    "+view-get-card",
    "+view-get-timebar",
)


def _view_config_commands(view):
    metadata = view.get("_meta")
    if not isinstance(metadata, dict):
        return VIEW_CONFIG_COMMANDS
    commands = ["+view-get-visible-fields"]
    if metadata.get("filter"):
        commands.append("+view-get-filter")
    if metadata.get("group"):
        commands.append("+view-get-group")
    if metadata.get("sort"):
        commands.append("+view-get-sort")
    view_type = view.get("view_type") or view.get("type")
    if view_type in ("gallery", "kanban"):
        commands.append("+view-get-card")
    if view_type in ("calendar", "gantt"):
        commands.append("+view-get-timebar")
    return tuple(commands)


def _unwrap(payload):
    if not isinstance(payload, dict):
        raise ValueError("lark-cli did not return a JSON object")
    if payload.get("ok") is False:
        raise RuntimeError(str(payload.get("error") or "lark-cli request failed"))
    return payload.get("data", payload)


def _items(payload):
    data = _unwrap(payload)
    for key in ("items", "tables", "fields", "views", "records"):
        value = data.get(key)
        if isinstance(value, list):
            return value, data
    return [], data


def _run_json(argv):
    result = subprocess.run(argv, text=True, capture_output=True)
    raw = result.stdout.strip() or result.stderr.strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"lark-cli returned non-JSON output for {argv[2]}") from error
    if result.returncode != 0:
        raise RuntimeError(str(payload.get("error") or f"lark-cli exited {result.returncode}"))
    return payload


def _page(cli, command, base_token, limit, table_id=None):
    offset = 0
    output = []
    while True:
        argv = ["lark-cli", "base", command, "--as", "user", "--base-token", base_token]
        if table_id:
            argv.extend(["--table-id", table_id])
        argv.extend(["--offset", str(offset), "--limit", str(limit)])
        if command == "+record-list":
            argv.extend(["--format", "json"])
        page, metadata = _items(cli(argv))
        output.extend(page)
        total = metadata.get("total")
        has_more = metadata.get("has_more")
        if not page:
            break
        offset += len(page)
        if isinstance(total, int) and offset >= total:
            break
        if has_more is False and total is None:
            break
        if has_more is not True and total is None and len(page) < limit:
            break
    return output


def _page_records(cli, base_token, table_id, limit):
    offset = 0
    output = []
    revision = None
    while True:
        argv = ["lark-cli", "base", "+record-list", "--as", "user", "--base-token", base_token,
                "--table-id", table_id, "--offset", str(offset), "--limit", str(limit), "--format", "json"]
        payload = cli(argv)
        data = _unwrap(payload)
        if all(key in data for key in ("fields", "record_id_list", "data")):
            fields = data["fields"]
            record_ids = data["record_id_list"]
            rows = data["data"]
            if len(record_ids) != len(rows) or any(len(row) != len(fields) for row in rows):
                raise ValueError("invalid columnar record-list response")
            page = [{"record_id": record_id, "fields": dict(zip(fields, row))}
                    for record_id, row in zip(record_ids, rows)]
        else:
            page, data = _items(payload)
        page_revision = data.get("rev")
        if page_revision is not None:
            if revision is not None and revision != page_revision:
                raise SourceChanged(f"table {table_id} changed during pagination")
            revision = page_revision
        output.extend(page)
        total = data.get("total")
        has_more = data.get("has_more")
        if not page:
            break
        offset += len(page)
        if isinstance(total, int) and offset >= total:
            break
        if has_more is False and total is None:
            break
        if has_more is not True and total is None and len(page) < limit:
            break
    return output, revision


def _clean(value, removed_keys=()):
    if isinstance(value, dict):
        return {key: _clean(item, removed_keys) for key, item in sorted(value.items()) if key not in removed_keys}
    if isinstance(value, list):
        return [_clean(item, removed_keys) for item in value]
    return value


def _replace_ids(value, id_to_name):
    if isinstance(value, dict):
        return {key: _replace_ids(item, id_to_name) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_ids(item, id_to_name) for item in value]
    if isinstance(value, str):
        return id_to_name.get(value, value)
    return value


def _replace_link_record_ids(value, record_ids):
    if isinstance(value, dict):
        return {
            key: record_ids.get(item, item) if key in ("id", "record_id") and isinstance(item, str)
            else _replace_link_record_ids(item, record_ids)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_link_record_ids(item, record_ids) for item in value]
    return value


def _attachment_items(value):
    return bool(value) and isinstance(value, list) and all(
        isinstance(item, dict) and item.get("file_token") for item in value
    )


def _safe_attachment(item):
    allowed = ("file_token", "name", "size", "mime_type", "type", "width", "height", "sha256", "format", "output_path")
    return {key: item[key] for key in allowed if item.get(key) is not None}


def _view_configs(cli, base_token, table_id, view, field_ids):
    view_id = view.get("view_id") or view.get("id")
    argv = ["lark-cli", "base", "+view-get-visible-fields", "--as", "user", "--base-token", base_token,
            "--table-id", table_id, "--view-id", view_id]
    id_to_name = {field_id: name for name, field_id in field_ids.items()}
    basic = _replace_ids(_clean(view, ("view_id", "table_id", "id", "view_name", "name", "view_type", "type")), id_to_name)
    result = {
        "name": view.get("view_name") or view.get("name"),
        "type": view.get("view_type") or view.get("type"),
        "basic": basic,
    }
    for command in _view_config_commands(view):
        argv[2] = command
        try:
            result[command.removeprefix("+view-get-")] = _replace_ids(_clean(_unwrap(cli(argv))), id_to_name)
        except RuntimeError as error:
            message = str(error).lower()
            if "not support" in message or "unsupported" in message or "view type" in message:
                result[command.removeprefix("+view-get-")] = {"status": "unsupported"}
            else:
                raise
    return result


def _capture_once(base_token, cli, role, record_map):
    tables = []
    mapping_tables = (record_map or {}).get("tables", {})
    record_ids = {
        source_id: target_id
        for table_mapping in mapping_tables.values()
        for source_id, target_id in table_mapping.get("records", {}).items()
    }
    table_ids = {
        source_id: table_mapping["target_table_id"]
        for source_id, table_mapping in mapping_tables.items()
        if table_mapping.get("target_table_id")
    }
    for raw_table in _page(cli, "+table-list", base_token, 100):
        table_id = raw_table.get("table_id") or raw_table.get("id")
        table_name = raw_table.get("table_name") or raw_table.get("name")
        raw_fields = _page(cli, "+field-list", base_token, 200, table_id)
        field_ids = {}
        fields = []
        attachment_fields = set()
        link_fields = set()
        for raw_field in raw_fields:
            field_id = raw_field.get("field_id") or raw_field.get("id")
            field_name = raw_field.get("field_name") or raw_field.get("name")
            field_ids[field_name] = field_id
            semantic = _clean(raw_field, ("field_id", "table_id", "id"))
            semantic["name"] = semantic.pop("field_name", field_name)
            if role == "source":
                semantic = _replace_ids(semantic, table_ids)
            fields.append(semantic)
            if raw_field.get("type") in (17, "attachment"):
                attachment_fields.add(field_name)
            if raw_field.get("type") in (18, 21, "link"):
                link_fields.add(field_name)
        fields.sort(key=lambda item: item["name"])
        raw_views = _page(cli, "+view-list", base_token, 200, table_id)
        views = [_view_configs(cli, base_token, table_id, view, field_ids) for view in raw_views]
        views.sort(key=lambda item: item["name"])
        raw_records, record_revision = _page_records(cli, base_token, table_id, 200)
        records = []
        table_mapping = mapping_tables.get(table_id, {})
        for raw_record in raw_records:
            record_id = raw_record.get("record_id") or raw_record.get("id")
            raw_values = raw_record.get("fields") or raw_record.get("values") or {}
            values = {}
            attachments = {}
            for raw_key, value in raw_values.items():
                field_name = next((name for name, field_id in field_ids.items() if field_id == raw_key), raw_key)
                if field_name in attachment_fields or _attachment_items(value):
                    attachments[field_name] = [_safe_attachment(item) for item in (value or [])]
                else:
                    cleaned = _clean(value)
                    if role == "source" and field_name in link_fields:
                        cleaned = _replace_link_record_ids(cleaned, record_ids)
                    values[field_name] = cleaned
            if role == "source":
                record = {"source_record_id": record_id, "values": values, "attachments": attachments}
                target_id = table_mapping.get("records", {}).get(record_id)
                if target_id:
                    record["target_record_id"] = target_id
            else:
                record = {"record_id": record_id, "values": values, "attachments": attachments}
            records.append(record)
        records.sort(key=lambda item: item.get("source_record_id") or item.get("record_id"))
        table = {"name": table_name, "fields": fields, "views": views, "records": records}
        if role == "source":
            table["source_table_id"] = table_id
            table["source_field_ids"] = field_ids
            if record_revision is not None:
                table["source_rev"] = record_revision
            target_table_id = table_mapping.get("target_table_id")
            if target_table_id:
                table["target_table_id"] = target_table_id
        else:
            table["table_id"] = table_id
            table["field_ids"] = field_ids
            if record_revision is not None:
                table["target_rev"] = record_revision
        tables.append(table)
    return {"manifest_version": 1, "role": role, "base_token": base_token, "tables": tables}


def _digest(manifest):
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def capture_stable(base_token, cli=_run_json, role="source", record_map=None, passes=None):
    if role not in ("source", "target"):
        raise ValueError("role must be source or target")
    pass_count = passes if passes is not None else (2 if role == "source" else 1)
    if pass_count not in (1, 2):
        raise ValueError("passes must be 1 or 2")
    first = _capture_once(base_token, cli, role, record_map)
    if pass_count == 2:
        second = _capture_once(base_token, cli, role, record_map)
        if _digest(first) != _digest(second):
            raise SourceChanged("Base changed between the two manifest reads")
    result = copy.deepcopy(first)
    result["snapshot_digest"] = _digest(first)
    result["stability"] = "double-read" if pass_count == 2 else "single-read"
    result["captured_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return result


def write_private(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser(description="Capture a semantic Lark Base replica manifest")
    parser.add_argument("--base-token", required=True)
    parser.add_argument("--role", choices=("source", "target"), required=True)
    parser.add_argument("--record-map")
    parser.add_argument("--passes", type=int, choices=(1, 2))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    record_map = None
    if args.record_map:
        with open(args.record_map, encoding="utf-8") as handle:
            record_map = json.load(handle)
    manifest = capture_stable(args.base_token, role=args.role, record_map=record_map, passes=args.passes)
    write_private(args.output, manifest)
    print(json.dumps({"tables": len(manifest["tables"]), "snapshot_digest": manifest["snapshot_digest"], "stability": manifest["stability"]}))


if __name__ == "__main__":
    main()
