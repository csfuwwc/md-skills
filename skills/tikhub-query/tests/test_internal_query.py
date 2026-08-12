import importlib.util
import contextlib
import io
import json
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tikhub_query.py"
spec = importlib.util.spec_from_file_location("tikhub_query_internal", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Completed:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


class FakeTransport:
    def __init__(self):
        self.requests = []

    def request(self, method, path, body=None, headers=None):
        self.requests.append(
            {"method": method, "path": path, "body": body, "headers": headers or {}}
        )
        return 200, {"ok": True, "response": {"aweme_id": "7645609920322112798"}}


class InternalQueryTests(unittest.TestCase):
    def test_cli_error_keeps_gateway_usage_receipt(self):
        gateway_response = {
            "ok": False,
            "error": "TikHub billing status is unknown",
            "usage": {
                "request_id": "request-preview",
                "billing_status": "unknown",
                "units": 1,
            },
        }
        original_run_cli = module.run_cli
        module.run_cli = lambda: (_ for _ in ()).throw(
            module.ClientError("TikHub query failed (HTTP 502)", gateway_response)
        )
        stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(module.main(), 1)
        finally:
            module.run_cli = original_run_cli

        self.assertEqual(
            json.loads(stderr.getvalue()),
            {
                "ok": False,
                "error": "TikHub query failed (HTTP 502)",
                "gateway_response": gateway_response,
            },
        )

    def test_query_attaches_current_feishu_identity_without_personal_token(self):
        def fake_run(_argv, **_kwargs):
            return Completed(
                json.dumps(
                    {
                        "ok": True,
                        "data": {
                            "user": {
                                "tenant_key": "tenant-company",
                                "open_id": "ou_alice",
                                "name": "Alice",
                            }
                        },
                    }
                )
            )

        transport = FakeTransport()
        client = module.TikHubClient(
            transport=transport,
            identity_reader=module.LarkIdentityReader(run=fake_run),
            uuid_factory=lambda: "internal-query-key",
        )
        result = client.query(
            "https://www.tiktok.com/@blindboxbrando/video/7645609920322112798"
        )
        self.assertTrue(result["ok"])
        request = transport.requests[0]
        self.assertEqual(request["path"], "/tikhub/search")
        self.assertEqual(
            request["body"]["caller"],
            {
                "tenant_key": "tenant-company",
                "open_id": "ou_alice",
                "name": "Alice",
            },
        )
        self.assertEqual(
            request["body"]["source_url"],
            "https://www.tiktok.com/@blindboxbrando/video/7645609920322112798",
        )
        self.assertEqual(request["headers"]["Idempotency-Key"], "internal-query-key")
        self.assertNotIn("Authorization", request["headers"])
        self.assertNotIn("X-API-Key", request["headers"])

    def test_default_gateway_is_company_internal_http_endpoint(self):
        self.assertEqual(module.DEFAULT_GATEWAY, "http://api-ai.modianinc.com:8080")

    def test_cli_exposes_only_simple_internal_commands(self):
        parser = module.build_parser()
        for command in ("query", "status", "doctor"):
            arguments = [command]
            if command == "query":
                arguments += [
                    "--url",
                    "https://www.tiktok.com/@blindboxbrando/video/7645609920322112798",
                ]
            self.assertEqual(parser.parse_args(arguments).command, command)
        for removed in ("prepare", "approve", "logout"):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args([removed])


if __name__ == "__main__":
    unittest.main()
