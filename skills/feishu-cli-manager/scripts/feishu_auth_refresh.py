#!/usr/bin/env python3
"""Check and refresh local lark-cli user authorization."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


def run_lark(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["lark-cli", *args],
        check=False,
        text=True,
        capture_output=True,
    )


def parse_json_output(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def parse_time(raw: Any) -> datetime | None:
    if not isinstance(raw, str) or not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def minutes_until(value: datetime | None) -> float | None:
    if value is None:
        return None
    return (value - datetime.now(value.tzinfo)).total_seconds() / 60


def format_minutes(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value < 0:
        return f"expired {abs(value):.0f} min ago"
    if value < 120:
        return f"{value:.0f} min"
    return f"{value / 60:.1f} h"


def status_payload(verify: bool) -> tuple[int, dict[str, Any] | None, str]:
    args = ["auth", "status"]
    if verify:
        args.append("--verify")
    result = run_lark(args)
    payload = parse_json_output(result.stdout)
    details = result.stdout.strip() or result.stderr.strip()
    return result.returncode, payload, details


def needs_login(payload: dict[str, Any] | None, renew_within_minutes: int) -> tuple[bool, str]:
    if payload is None:
        return True, "auth status was unavailable or not JSON"

    token_status = str(payload.get("tokenStatus") or "").lower()
    identity = str(payload.get("identity") or "").lower()
    expires_in = minutes_until(parse_time(payload.get("expiresAt")))
    refresh_expires_in = minutes_until(parse_time(payload.get("refreshExpiresAt")))

    if identity and identity != "user":
        return False, f"current identity is {identity}; auth login is only for user auth"
    if token_status != "valid":
        return True, f"tokenStatus is {payload.get('tokenStatus') or 'unknown'}"
    if refresh_expires_in is not None and refresh_expires_in <= 0:
        return True, "refresh token is expired"
    if expires_in is not None and expires_in <= renew_within_minutes:
        return True, f"access token expires within {renew_within_minutes} min"
    return False, "token is valid"


def print_status(payload: dict[str, Any] | None, reason: str, renew_within_minutes: int) -> None:
    print("Feishu CLI auth status")
    print(f"- lark-cli: {shutil.which('lark-cli') or 'not found'}")
    if payload is None:
        print(f"- status: unavailable ({reason})")
        return

    expires_at = parse_time(payload.get("expiresAt"))
    refresh_expires_at = parse_time(payload.get("refreshExpiresAt"))
    print(f"- identity: {payload.get('identity') or 'unknown'}")
    print(f"- tokenStatus: {payload.get('tokenStatus') or 'unknown'}")
    print(f"- userName: {payload.get('userName') or 'unknown'}")
    print(f"- expiresAt: {payload.get('expiresAt') or 'unknown'} ({format_minutes(minutes_until(expires_at))})")
    print(
        "- refreshExpiresAt: "
        f"{payload.get('refreshExpiresAt') or 'unknown'} ({format_minutes(minutes_until(refresh_expires_at))})"
    )
    print(f"- renew window: {renew_within_minutes} min")
    print(f"- decision: {reason}")


def login_args(args: argparse.Namespace) -> list[str]:
    command = ["auth", "login"]
    for domain in args.domain:
        command.extend(["--domain", domain])
    if args.scope:
        command.extend(["--scope", args.scope])
    if args.recommend:
        command.append("--recommend")
    if not args.domain and not args.scope and not args.recommend:
        command.append("--recommend")
    if args.no_wait:
        command.extend(["--no-wait", "--json"])
    return command


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and refresh lark-cli auth.")
    parser.add_argument("--verify", action="store_true", help="Verify token against the server.")
    parser.add_argument(
        "--renew-within-minutes",
        type=int,
        default=30,
        help="Treat access tokens expiring within this window as needing renewal.",
    )
    parser.add_argument("--login-if-needed", action="store_true", help="Run auth login when status needs it.")
    parser.add_argument("--force-login", action="store_true", help="Always start auth login.")
    parser.add_argument("--domain", action="append", default=[], help="Domain to request; repeatable.")
    parser.add_argument("--scope", default="", help="Scopes to request, space- or comma-separated.")
    parser.add_argument("--recommend", action="store_true", help="Request recommended scopes.")
    parser.add_argument("--no-wait", action="store_true", help="Return device-flow JSON instead of waiting.")
    args = parser.parse_args()

    if shutil.which("lark-cli") is None:
        print("lark-cli was not found on PATH", file=sys.stderr)
        return 127

    code, payload, details = status_payload(args.verify)
    login_needed, reason = needs_login(payload, args.renew_within_minutes)
    print_status(payload, reason, args.renew_within_minutes)

    if code != 0 and details:
        print("\nRaw status output:")
        print(details)
        lower_details = details.lower()
        if "keychain" in lower_details and "not initialized" in lower_details:
            print(
                "\nHint: lark-cli needs keychain access. In Codex, run direct "
                "`lark-cli auth status` commands or run this helper outside the sandbox."
            )

    if not args.force_login and not (args.login_if_needed and login_needed):
        return 0 if not login_needed else 2

    command = login_args(args)
    print("\nStarting lark-cli authorization...")
    print(f"- requested domains: {', '.join(args.domain) if args.domain else 'none'}")
    print(f"- requested scopes: {args.scope or 'none'}")
    print(f"- recommend: {bool(args.recommend or (not args.domain and not args.scope))}")

    result = run_lark(command)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
