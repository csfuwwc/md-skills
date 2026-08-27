---
name: lark-base-replica
description: 复刻或迁移当前用户可合法查看但无法直接复制的飞书多维表格到自己的 Base，包含表、字段、视图、支持的普通记录和可见附件。适用于完全复刻、复制、迁移、备份或重建外部多维表格；源表保持只读，写入前必须确认精确目标 Base。
metadata:
  version: 1.0.1
---

# Lark Base Replica

Build an evidence-backed replica without claiming access to invisible platform objects. Use the run ledger as coordination evidence; live Feishu remains the source of truth.

## Prerequisites

1. Read `../lark-shared/SKILL.md` and `../lark-base/SKILL.md` completely.
2. Read each `lark-base` command reference before invoking that command.
3. Read `references/capability-ladder.md` before selecting the extraction path.
4. Read the Browser control Skill and `references/feishu-cdp-attachments.md` only when visible attachments cannot be recovered through the official path.
5. Read `references/acceptance-contract.md` before planning or reporting, and `references/release-gates.md` when changing this Skill.

## Non-negotiable boundaries

- Operate only on content the current signed-in user can normally view. Keep the source Base read-only.
- Never read browser cookies, local storage, profiles, password stores, tokens, or cryptographic material.
- Obtain authorization naming the exact target Base and write scope immediately before any external write. Prior read/extraction approval is not write approval.
- Do not promise `100%`. Claim only the domains with zero verified mismatches; report excluded or inaccessible objects separately.
- The supported contract covers tables, semantic field definitions, supported views, supported ordinary cells, and visible attachment content. Workflows, dashboards, forms, advanced permissions, comments, sharing, formulas/lookup behavior, and original attachment binaries require separate proof.
- The CDP fallback currently accepts only decrypted PNG, WebP, and JPEG display derivatives. Recover other attachment types through the official media path or report them as unverified.
- Keep manifests, mappings, and ledgers at mode `0600`. Delete signed URLs, AES material, and decrypted cache only after successful live readback and explicit cleanup confirmation.

## Resumable run

Use one private run directory per migration. `scripts/replica.py` enforces:

```text
NEW → PROBED → SNAPSHOTTED → PLANNED → STRUCTURE_WRITTEN
    → RECORDS_VERIFIED → ATTACHMENTS_VERIFIED → COMPLETE
```

### 1. Initialize and probe

Create the target Base only after the user authorizes that exact object. Then initialize the ledger and probe current CLI capabilities:

```bash
python3 <skill-dir>/scripts/replica.py init \
  --run-dir <private-run-dir> --source <source-base-token> --target <target-base-token>
python3 <skill-dir>/scripts/replica.py probe --run-dir <private-run-dir>
```

The attachment probe must explicitly find repeated `--file` append semantics for one attachment cell. If absent, attachment writes are blocked; do not guess or upload sequentially.

### 2. Capture stable manifests and plan

`snapshot` double-reads the source and stops if any semantic structure, record, or attachment metadata changes. It reads the target once.

```bash
python3 <skill-dir>/scripts/replica.py snapshot \
  --run-dir <private-run-dir> [--record-map <private-record-map.json>]
python3 <skill-dir>/scripts/replica.py plan --run-dir <private-run-dir>
```

The record map shape is documented in `references/acceptance-contract.md`. It normalizes source link-field table IDs and link-cell record IDs to their mapped target IDs. Never infer target IDs.

### 3. Write structure and ordinary data

Use the official `lark-cli base +...` shortcuts under the `lark-base` Skill. Exclude attachments and read-only/derived fields from ordinary writes. Batch at most 200 records and serialize writes within one table.

After each domain, recapture the live target with `scripts/capture_manifest.py`, then provide that manifest as evidence:

```bash
python3 <skill-dir>/scripts/replica.py apply \
  --run-dir <private-run-dir> --phase structure --evidence <target-after-structure.json> \
  --authorized-target <exact-target-base-token>
python3 <skill-dir>/scripts/replica.py apply \
  --run-dir <private-run-dir> --phase records --evidence <target-after-records.json> \
  --attachment-manifest <decrypted-dir/download-manifest.json> \
  --authorized-target <exact-target-base-token>
```

These checkpoints advance only when the relevant comparison has zero mismatches. The records checkpoint regenerates an idempotent attachment plan from live target state.

### 4. Recover and apply visible attachments

Use the official media path first. If it cannot recover an attachment that the user can visibly render, follow `references/feishu-cdp-attachments.md`. Decrypt mappings without retaining URL/key/nonce in the output manifest:

```bash
node <skill-dir>/scripts/decrypt_attachments.mjs \
  <private-cdn-map.json> <private-decrypted-dir> 8
```

Preview the generated attachment plan with `scripts/upload_attachments.py --dry-run`. Only after the user confirms the exact target and attachment write scope, run:

```bash
python3 <skill-dir>/scripts/replica.py apply \
  --run-dir <private-run-dir> --phase attachments \
  --evidence <target-after-records.json> \
  --authorized-target <exact-target-base-token> \
  --upload-root <private-run-dir/upload-ready> \
  --ephemeral-path <private-run-dir/private-cdn-map.json> \
  --ephemeral-path <private-run-dir/decrypted-dir>
```

The attachment manifest is merged by `file_token`; URL, AES, cookie, or access-token fields are rejected. Decrypted sources, registered ephemeral paths, and the upload root must be inside the run directory. The uploader verifies available SHA-256 metadata and rejects stale staging content. On the first ambiguous or retryable failure, stop. Re-read the target and retry the same attachment phase with that fresh target manifest as `--evidence`; the runner regenerates the plan and applies only missing files.

### 5. Verify and clean up

`verify` re-reads the live target; cached target data is never acceptance evidence.

```bash
python3 <skill-dir>/scripts/replica.py verify --run-dir <private-run-dir>
python3 <skill-dir>/scripts/replica.py cleanup --run-dir <private-run-dir> --confirmed
```

Cleanup is allowed only after `COMPLETE` and deletes only ephemeral paths explicitly registered inside the run directory. Preserve the final report and ledger.

## Failure rules

- Permission error or invisible content: stop that domain; do not switch identity or retry around the denial.
- Source double-read mismatch: stop and recapture; never merge two revisions silently.
- Unknown target attachment or extra target record: stop and preserve the possible user change.
- Missing multi-file append contract: block attachment writes and request approval before any CLI update.
- Final mismatch: report `partial` or `blocked`, with counts and the exact unverified domains.
