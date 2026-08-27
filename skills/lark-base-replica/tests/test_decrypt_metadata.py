import json
import pathlib
import subprocess
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "decrypt_attachments.mjs"


class DecryptMetadataTests(unittest.TestCase):
    def test_self_test_reports_safe_fidelity_metadata(self):
        result = subprocess.run(["node", str(SCRIPT), "--self-test"], text=True, capture_output=True, check=True)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["format"], "png")
        self.assertEqual(payload["width"], 1)
        self.assertEqual(payload["height"], 1)
        self.assertEqual(len(payload["sha256"]), 64)
        self.assertTrue(payload["secret_fields_removed"])


if __name__ == "__main__":
    unittest.main()
