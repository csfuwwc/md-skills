#!/usr/bin/env python3

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


DEFAULT_GATEWAY = "http://api-ai.modianinc.com:8080"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
VIDEO_PATH = re.compile(r"^/@[^/]*/video/(?P<video_id>[0-9]+)$")


class ClientError(RuntimeError):
    def __init__(self, message, gateway_response=None):
        super().__init__(message)
        self.gateway_response = gateway_response


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, _req, _fp, _code, _msg, _headers, _newurl):
        return None


class HTTPTransport:
    def __init__(self, opener=None):
        self.base_url = DEFAULT_GATEWAY
        self.opener = opener or urllib.request.build_opener(NoRedirect())

    def request(self, method, path, body=None, headers=None):
        if path not in {"/tikhub/search"}:
            raise ClientError("unsupported gateway path")
        encoded = None
        request_headers = {"Accept": "application/json"}
        request_headers.update(headers or {})
        if body is not None:
            encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=encoded,
            headers=request_headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                status = response.status
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status = exc.code
            payload = exc.read(MAX_RESPONSE_BYTES + 1)
        except (OSError, urllib.error.URLError) as exc:
            raise ClientError("gateway request failed") from exc
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ClientError("gateway response is too large")
        try:
            decoded = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ClientError("gateway returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise ClientError("gateway returned invalid JSON")
        return status, decoded


class LarkIdentityReader:
    def __init__(self, lark_cli="lark-cli", run=subprocess.run):
        self.lark_cli = lark_cli
        self.run = run

    def get(self):
        completed = self.run(
            [
                self.lark_cli,
                "contact",
                "+get-user",
                "--as",
                "user",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise ClientError("unable to read the current Feishu user identity")
        try:
            response = json.loads(completed.stdout)
            user = response["data"]["user"]
            tenant_key = user["tenant_key"].strip()
            open_id = user["open_id"].strip()
            name = user["name"].strip()
        except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
            raise ClientError("current Feishu user identity is incomplete") from None
        response_ok = (
            response.get("ok") is True
            if "ok" in response
            else response.get("code") == 0
        )
        if not response_ok or not tenant_key or len(tenant_key) > 128:
            raise ClientError("current Feishu user identity is incomplete")
        if not open_id.startswith("ou_") or len(open_id) > 128:
            raise ClientError("current Feishu user identity is incomplete")
        if not name or len(name) > 128:
            raise ClientError("current Feishu user identity is incomplete")
        return {"tenant_key": tenant_key, "open_id": open_id, "name": name}


def parse_tiktok_url(raw_url, shop_region=None):
    try:
        parsed = urllib.parse.urlsplit(raw_url)
    except ValueError as exc:
        raise ClientError("invalid TikTok URL") from exc
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in {"tiktok.com", "www.tiktok.com"}:
        raise ClientError("URL must use https://www.tiktok.com")
    if parsed.username or parsed.password or parsed.port is not None or parsed.fragment:
        raise ClientError("invalid TikTok URL")
    match = VIDEO_PATH.fullmatch(parsed.path.rstrip("/"))
    if match is None:
        raise ClientError("TikTok URL must contain /@user/video/<digits>")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    region = shop_region or (query.get("shop_region") or ["US"])[0]
    region = region.strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", region):
        raise ClientError("shop region must be a two-letter country code")
    return {
        "source_url": raw_url,
        "platform": "tiktok",
        "type": "video_detail",
        "keyword": match.group("video_id"),
        "params": {"region": region},
    }


class TikHubClient:
    def __init__(self, transport, identity_reader, uuid_factory=None):
        self.transport = transport
        self.identity_reader = identity_reader
        self.uuid_factory = uuid_factory or (lambda: "query_" + uuid.uuid4().hex)

    def status(self):
        return {
            "ok": True,
            "identity": self.identity_reader.get(),
            "gateway": DEFAULT_GATEWAY,
        }

    def query(self, tiktok_url, shop_region=None):
        request_body = parse_tiktok_url(tiktok_url, shop_region)
        request_body["caller"] = self.identity_reader.get()
        idempotency_key = self.uuid_factory()
        if not isinstance(idempotency_key, str) or not re.fullmatch(
            r"[A-Za-z0-9._:-]{8,128}", idempotency_key
        ):
            raise ClientError("unable to create query idempotency key")
        status, response = self.transport.request(
            "POST",
            "/tikhub/search",
            body=request_body,
            headers={"Idempotency-Key": idempotency_key},
        )
        if status != 200 or response.get("ok") is not True:
            raise ClientError(
                f"TikHub query failed (HTTP {status})",
                gateway_response=response,
            )
        return response


def build_default_app():
    return TikHubClient(HTTPTransport(), LarkIdentityReader())


def doctor():
    return {
        "ok": True,
        "python": platform.python_version(),
        "platform": sys.platform,
        "lark_cli": shutil.which("lark-cli") is not None,
        "gateway": DEFAULT_GATEWAY,
    }


def build_parser():
    parser = argparse.ArgumentParser(prog="tikhub-query")
    subparsers = parser.add_subparsers(dest="command", required=True)
    query_parser = subparsers.add_parser("query")
    query_parser.add_argument("--url", required=True)
    query_parser.add_argument("--shop-region")
    subparsers.add_parser("status")
    subparsers.add_parser("doctor")
    return parser


def run_cli(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        result = doctor()
    else:
        client = build_default_app()
        if args.command == "status":
            result = client.status()
        else:
            result = client.query(args.url, args.shop_region)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


def main():
    try:
        return run_cli()
    except ClientError as exc:
        payload = {"ok": False, "error": str(exc)}
        if exc.gateway_response is not None:
            payload["gateway_response"] = exc.gateway_response
        print(
            json.dumps(payload, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    except Exception:
        print(json.dumps({"ok": False, "error": "operation failed"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
