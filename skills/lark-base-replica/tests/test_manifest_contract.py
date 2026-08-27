import pathlib
import sys
import unittest


SCRIPTS = pathlib.Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from replica_manifest import compare_replica, plan_missing_attachments


def fixtures():
    source = {"tables": [{
        "name": "Prompts",
        "target_table_id": "tbl_target",
        "fields": [{"name": "Title", "type": 1}, {"name": "Images", "type": 17}],
        "views": [{"name": "All", "visible_fields": ["Title", "Images"]}],
        "records": [{"source_record_id": "rec_s", "target_record_id": "rec_t", "values": {"Title": "A"},
                     "attachments": {"Images": [{"file_token": "box_1", "name": "one.webp", "output_path": "/tmp/one.png"}]}}],
    }]}
    target = {"tables": [{
        "name": "Prompts", "table_id": "tbl_target",
        "fields": [{"type": 1, "name": "Title"}, {"type": 17, "name": "Images"}],
        "views": [{"visible_fields": ["Title", "Images"], "name": "All"}],
        "records": [{"record_id": "rec_t", "values": {"Title": "A"}, "attachments": {"Images": [{"name": "one.png"}]}}],
    }]}
    return source, target


class ManifestContractTests(unittest.TestCase):
    def test_compare_ignores_object_key_order_but_preserves_array_order(self):
        source, target = fixtures()
        self.assertEqual(compare_replica(source, target)["structure_mismatches"], [])
        target["tables"][0]["views"][0]["visible_fields"].reverse()
        self.assertEqual(compare_replica(source, target)["structure_mismatches"][0]["kind"], "views")

    def test_compare_reports_extra_target_records(self):
        source, target = fixtures()
        target["tables"][0]["records"].append({"record_id": "manual", "values": {}, "attachments": {}})
        report = compare_replica(source, target)
        self.assertEqual(report["value_mismatches"][0]["kind"], "record_set")

    def test_compare_reports_target_only_ordinary_cell(self):
        source, target = fixtures()
        target["tables"][0]["records"][0]["values"]["Unexpected"] = "manual edit"

        report = compare_replica(source, target)

        self.assertEqual(report["value_mismatches"][0]["kind"], "value_fields")

    def test_attachment_plan_is_idempotent_across_derivative_extensions(self):
        source, target = fixtures()
        self.assertEqual(plan_missing_attachments(source, target), [])
        target["tables"][0]["records"][0]["attachments"]["Images"] = []
        plan = plan_missing_attachments(source, target)
        self.assertEqual(plan[0]["files"][0]["file_token"], "box_1")

    def test_compare_and_plan_reject_target_only_attachment_field(self):
        source, target = fixtures()
        target_record = target["tables"][0]["records"][0]
        target_record["attachments"]["Manual"] = [{"name": "unexpected.png"}]

        report = compare_replica(source, target)

        self.assertEqual(report["attachment_mismatches"][0]["field"], "Manual")
        with self.assertRaisesRegex(ValueError, "target attachment not present in source"):
            plan_missing_attachments(source, target)

    def test_duplicate_attachment_stems_preserve_multiplicity(self):
        source, target = fixtures()
        source_files = [
            {"file_token": "box_1", "name": "same.webp", "output_path": "/tmp/box_1.png"},
            {"file_token": "box_2", "name": "same.jpg", "output_path": "/tmp/box_2.png"},
        ]
        source["tables"][0]["records"][0]["attachments"]["Images"] = source_files
        target_files = target["tables"][0]["records"][0]["attachments"]["Images"]
        target_files[0]["name"] = "same.png"

        plan = plan_missing_attachments(source, target)

        self.assertEqual(len(plan[0]["files"]), 1)
        target_files.append({"name": "same.avif"})
        self.assertEqual(compare_replica(source, target)["attachment_mismatches"], [])

    def test_date_people_and_link_values_require_exact_semantic_equality(self):
        source, target = fixtures()
        complex_values = {
            "When": "2026-08-27 10:30:00",
            "Owners": [{"id": "ou_owner"}, {"id": "ou_reviewer"}],
            "Related": [{"id": "rec_related"}],
        }
        source["tables"][0]["records"][0]["values"].update(complex_values)
        target["tables"][0]["records"][0]["values"].update(complex_values)
        self.assertEqual(compare_replica(source, target)["value_mismatches"], [])

        target["tables"][0]["records"][0]["values"]["Related"] = [{"id": "rec_other"}]
        mismatches = compare_replica(source, target)["value_mismatches"]
        self.assertEqual(mismatches[0]["field"], "Related")


if __name__ == "__main__":
    unittest.main()
