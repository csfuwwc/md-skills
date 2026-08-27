import pathlib
import sys
import unittest


SCRIPTS = pathlib.Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from capture_manifest import SourceChanged, capture_stable


class FakeCli:
    def __init__(self, mutate_second_pass=False):
        self.calls = []
        self.record_reads = 0
        self.mutate_second_pass = mutate_second_pass

    def __call__(self, argv):
        self.calls.append(tuple(argv))
        command = argv[2]
        offset = int(argv[argv.index("--offset") + 1]) if "--offset" in argv else 0
        table_id = argv[argv.index("--table-id") + 1] if "--table-id" in argv else None
        view_id = argv[argv.index("--view-id") + 1] if "--view-id" in argv else None
        if command == "+table-list":
            return {"ok": True, "data": {"items": [{"table_id": "tbl_src", "table_name": "Prompts"}], "total": 1}}
        if command == "+field-list":
            return {"ok": True, "data": {"items": [
                {"field_id": "fld_title", "field_name": "Title", "type": 1, "property": {}},
                {"field_id": "fld_images", "field_name": "Images", "type": 17, "property": {}},
            ], "total": 2}}
        if command == "+view-list":
            return {"ok": True, "data": {"views": [{"view_id": "viw_grid", "view_name": "All", "view_type": "grid"}], "total": 1}}
        if command == "+view-get":
            return {"ok": True, "data": {"view_id": view_id, "view_name": "All", "view_type": "grid"}}
        if command.startswith("+view-get-"):
            return {"ok": True, "data": {"items": []}}
        if command == "+record-list":
            self.record_reads += 1
            pass_number = (self.record_reads - 1) // 2
            records = [
                {"record_id": "rec_s1", "fields": {"Title": "A" if not (self.mutate_second_pass and pass_number) else "CHANGED", "Images": [{"file_token": "box_1", "name": "one.webp"}]}},
                {"record_id": "rec_s2", "fields": {"Title": "B", "Images": []}},
            ]
            return {"ok": True, "data": {"items": [records[offset]] if offset < 2 else [], "total": 2, "has_more": offset < 1}}
        raise AssertionError((command, table_id, view_id, offset))


class RealEnvelopeCli:
    def __init__(self):
        self.calls = []
        self.field_reads = 0

    def __call__(self, argv):
        self.calls.append(tuple(argv))
        command = argv[2]
        offset = int(argv[argv.index("--offset") + 1]) if "--offset" in argv else 0
        view_id = argv[argv.index("--view-id") + 1] if "--view-id" in argv else None
        if command == "+table-list":
            return {"ok": True, "data": {"tables": [{"id": "tbl_src", "name": "Prompts", "records_count": 2, "rev": 149}], "total": 1}}
        if command == "+field-list":
            self.field_reads += 1
            fields = [
                {"id": "fld_title", "name": "Title", "type": "text", "style": {"type": "plain"}},
                {"id": "fld_when", "name": "When", "type": "datetime"},
                {"id": "fld_owners", "name": "Owners", "type": "user", "multiple": True},
                {"id": "fld_related", "name": "Related", "type": "link", "multiple": True,
                 "link_table": "tbl_related"},
                {"id": "fld_images", "name": "Images", "type": "attachment"},
            ]
            if self.field_reads % 2 == 0:
                fields.reverse()
            return {"ok": True, "data": {"fields": fields, "total": 2}}
        if command == "+view-list":
            return {"ok": True, "data": {"views": [{"id": "vew_grid", "name": "All", "type": "grid", "_meta": {"visible_fields": "2 fields"}}], "total": 1}}
        if command == "+view-get":
            return {"ok": True, "data": {"view": {"id": view_id, "name": "All", "type": "grid"}}}
        if command.startswith("+view-get-"):
            return {"ok": True, "data": {"visible_fields": ["Title", "Images"]} if command.endswith("visible-fields") else {}}
        if command == "+record-list":
            rows = [
                ("rec_s1", ["A", "2026-08-27 10:30:00", [{"id": "ou_owner"}], [{"id": "rec_related"}],
                             [{"file_token": "box_1", "name": "one.webp"}]]),
                ("rec_s2", ["B", None, [], [], None]),
            ]
            record_id, row = rows[offset]
            return {"ok": True, "data": {
                "fields": ["Title", "When", "Owners", "Related", "Images"],
                "field_type_list": ["text", "datetime", "user", "link", "attachment"],
                "record_id_list": [record_id],
                "data": [row],
                "rev": 149,
                "total": 2,
                "has_more": offset == 0,
            }}
        raise AssertionError(command)


class CaptureManifestTests(unittest.TestCase):
    def test_double_read_captures_semantic_manifest_and_mapping(self):
        cli = FakeCli()
        mapping = {"tables": {"tbl_src": {"target_table_id": "tbl_target", "records": {"rec_s1": "rec_t1", "rec_s2": "rec_t2"}}}}

        manifest = capture_stable("app_source", cli, role="source", record_map=mapping)

        self.assertEqual(manifest["stability"], "double-read")
        self.assertEqual(manifest["tables"][0]["target_table_id"], "tbl_target")
        self.assertEqual(manifest["tables"][0]["records"][0]["target_record_id"], "rec_t1")
        self.assertEqual(manifest["tables"][0]["records"][0]["values"], {"Title": "A"})
        self.assertEqual(manifest["tables"][0]["records"][0]["attachments"]["Images"][0]["file_token"], "box_1")
        record_offsets = [call[call.index("--offset") + 1] for call in cli.calls if call[2] == "+record-list"]
        self.assertEqual(record_offsets, ["0", "1", "0", "1"])

    def test_double_read_stops_when_source_changes(self):
        with self.assertRaises(SourceChanged):
            capture_stable("app_source", FakeCli(mutate_second_pass=True), role="source")

    def test_current_cli_envelopes_capture_tables_fields_columnar_records_and_revision(self):
        cli = RealEnvelopeCli()
        mapping = {"tables": {
            "tbl_src": {"target_table_id": "tbl_target", "records": {"rec_s1": "rec_t1", "rec_s2": "rec_t2"}},
            "tbl_related": {"target_table_id": "tbl_related_target", "records": {"rec_related": "rec_related_target"}},
        }}

        manifest = capture_stable("app_source", cli, role="source", record_map=mapping)

        table = manifest["tables"][0]
        self.assertEqual(table["name"], "Prompts")
        self.assertEqual([field["name"] for field in table["fields"]], ["Images", "Owners", "Related", "Title", "When"])
        self.assertEqual(table["source_rev"], 149)
        self.assertEqual([record["source_record_id"] for record in table["records"]], ["rec_s1", "rec_s2"])
        self.assertEqual(table["records"][0]["values"], {
            "Title": "A",
            "When": "2026-08-27 10:30:00",
            "Owners": [{"id": "ou_owner"}],
            "Related": [{"id": "rec_related_target"}],
        })
        self.assertEqual(table["records"][0]["attachments"]["Images"][0]["file_token"], "box_1")
        self.assertEqual(table["records"][1]["values"]["Owners"], [])
        self.assertEqual(table["records"][1]["values"]["Related"], [])
        self.assertEqual(table["records"][1]["attachments"]["Images"], [])
        self.assertNotIn("Owners", table["records"][1]["attachments"])
        self.assertNotIn("Related", table["records"][1]["attachments"])
        related_field = next(field for field in table["fields"] if field["name"] == "Related")
        self.assertEqual(related_field["link_table"], "tbl_related_target")
        called = {call[2] for call in cli.calls}
        self.assertIn("+view-get-visible-fields", called)
        self.assertNotIn("+view-get", called)
        self.assertNotIn("+view-get-filter", called)
        self.assertNotIn("+view-get-card", called)


if __name__ == "__main__":
    unittest.main()
