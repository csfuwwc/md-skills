---
name: feishu-cli-manager
description: Use when the user asks to install Feishu/Lark CLI, configure lark-cli, connect an agent with Feishu CLI, check or refresh lark-cli auth, recover expired tokens, or start a Feishu device-flow login.
---

# Feishu CLI Manager

Use this skill to install, configure, and maintain local `lark-cli` for agent workflows.

## Core Rules

- Never print app secrets, access tokens, refresh tokens, cookies, or credential files.
- Treat `which lark-cli`, `lark-cli --version`, and `npm list -g --depth=0` as installation evidence.
- Treat `lark-cli auth status` as the first source of truth for local auth state.
- Use `lark-cli auth status --verify` only when network verification is needed.
- User auth and bot auth are different. Do not run `auth login` for bot-only permission issues.
- `lark-cli auth login` must request an explicit range with `--domain`, `--scope`, or `--recommend`.
- When command output contains a verification URL, copy that URL exactly as returned. Do not rewrite or re-encode it.
- Do not run `lark-cli config bind`, `lark-cli config init --new`, or `lark-cli config init --force-init` unless the user confirms the intended app/config identity.

## Install Check

Prefer the bundled helper when available from this skill directory:

```bash
python3 scripts/feishu_cli_setup.py --check
```

Manual checks:

```bash
node --version
npm --version
which lark-cli
lark-cli --version
```

`lark-cli` is normally installed as the global npm package `@larksuite/cli`.

## Install Or Update

Install only when `lark-cli` is missing:

```bash
python3 scripts/feishu_cli_setup.py --install
```

Equivalent direct command:

```bash
npm install -g @larksuite/cli
```

Update an existing install:

```bash
lark-cli update
```

Use `lark-cli update --check --json` when only checking update availability.

## Configure

If `lark-cli` is installed but not configured, inspect before changing anything:

```bash
lark-cli auth status
lark-cli config init --help
lark-cli config bind --help
```

Inside an agent workspace, prefer `lark-cli config bind` only after the user confirms the target app and identity mode. Use `bot-only` unless the task needs personal resources; use `user-default` only when the user explicitly needs user-resource access.

For a brand-new standalone app setup, and only after the user confirms that intent:

```bash
lark-cli config init --new
```

## Auth Check

Run:

```bash
lark-cli auth status
```

Use server verification only when needed:

```bash
lark-cli auth status --verify
```

If an environment reports `keychain not initialized`, first suspect that the current process cannot access the local keychain. Re-run the check in an environment with normal keychain access before assuming the Feishu account or token is broken.

## Refresh Or Reconnect

If the token is expired, missing, revoked, or too close to expiry, start a scoped login:

```bash
lark-cli auth login --domain all --scope offline_access
```

Use narrower domains or scopes when the task is limited:

```bash
lark-cli auth login --domain docs --domain drive
lark-cli auth login --scope "docs:document.content:read drive:file:download offline_access"
```

The bundled helper can summarize expiry and decide whether login is needed, but it must run with the same keychain access as `lark-cli`:

```bash
python3 scripts/feishu_auth_refresh.py --login-if-needed --domain all --scope offline_access
```

## Agent Workflow

1. Check whether `lark-cli` is installed.
2. If missing, install `@larksuite/cli` with npm after confirming Node/npm are available.
3. If installed but not configured, decide between binding an existing agent app and creating a new app; do not guess this choice.
4. Check auth state with `lark-cli auth status`.
5. If `tokenStatus` is valid and `refreshExpiresAt` is not close, report that no reconnect is needed.
6. If access token expiry is close but refresh token is still valid, run `lark-cli auth status --verify` once and re-check.
7. If refresh token is expired, missing, or revoked, start `lark-cli auth login` with the smallest explicit domain/scope that fits the task.
8. If a device-flow URL is returned, present it exactly and wait for the user to authorize.
9. Verify completion with `lark-cli auth status --verify`.
