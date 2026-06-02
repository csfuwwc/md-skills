#!/usr/bin/env python3
"""Install and inspect local lark-cli setup."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys


PACKAGE_NAME = "@larksuite/cli"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, text=True, capture_output=True)


def print_result(label: str, result: subprocess.CompletedProcess[str]) -> None:
    output = (result.stdout or result.stderr).strip()
    print(f"- {label}: {'ok' if result.returncode == 0 else 'failed'}")
    if output:
        first_line = output.splitlines()[0]
        print(f"  {first_line}")


def check_tool(name: str, version_args: list[str]) -> bool:
    path = shutil.which(name)
    print(f"- {name}: {path or 'not found'}")
    if not path:
        return False
    result = run([name, *version_args])
    print_result(f"{name} version", result)
    return result.returncode == 0


def check_install() -> tuple[bool, bool, bool]:
    print("Feishu CLI install check")
    has_node = check_tool("node", ["--version"])
    has_npm = check_tool("npm", ["--version"])
    has_lark = check_tool("lark-cli", ["--version"])
    if has_npm:
        result = run(["npm", "list", "-g", "--depth=0"])
        package_line = ""
        for line in result.stdout.splitlines():
            if PACKAGE_NAME in line:
                package_line = line.strip()
                break
        print(f"- npm package: {package_line or 'not found in global npm list'}")
    return has_node, has_npm, has_lark


def install_lark_cli(force: bool) -> int:
    has_node, has_npm, has_lark = check_install()
    if not has_node or not has_npm:
        print("\nNode.js and npm are required before installing lark-cli.", file=sys.stderr)
        return 2
    if has_lark and not force:
        print("\nlark-cli is already installed. Use --force to reinstall.")
        return 0

    print(f"\nInstalling {PACKAGE_NAME} with npm...")
    result = run(["npm", "install", "-g", PACKAGE_NAME])
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    if result.returncode != 0:
        return result.returncode

    print("\nPost-install check")
    check_install()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install and inspect lark-cli.")
    parser.add_argument("--check", action="store_true", help="Check Node, npm, and lark-cli.")
    parser.add_argument("--install", action="store_true", help="Install @larksuite/cli if missing.")
    parser.add_argument("--force", action="store_true", help="Reinstall even if lark-cli exists.")
    args = parser.parse_args()

    if args.install:
        return install_lark_cli(args.force)

    check_install()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
