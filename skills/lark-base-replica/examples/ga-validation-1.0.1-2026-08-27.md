# GA live requalification — 1.0.1 — 2026-08-27

Result: pass
CLI: lark-cli 1.0.90
Identity: verified user
Scope: retained disposable source/target plus the retained authorized large migration
Secrets retained in this report: none

## Automated gates

- 25/25 unit tests passed after observing the new regression tests fail before implementation.
- Python syntax checks, Node syntax check, and Skill quick validation passed.
- Current CLI help explicitly promises repeated `--file` append, multiple attachments in one cell, and a maximum of 50 files.
- Target-only ordinary fields and target-only attachment fields are now detected bidirectionally.
- Evidence manifests are bound to manifest version 1, `role=target`, and the exact authorized target Base.
- Attachment source paths are restricted to the private run directory; available SHA-256 metadata and stale staged content are checked.
- The uploader stops after the first failed job; the additional live probe involving a second valid cell was not executed because it exceeded the confirmed write scope, so this invariant remains automated-test evidence.

## Case 1 — current small complex-field Base

- The source was recaptured with a stable double read and the target with a single live read using the 1.0.1 code.
- Coverage: 3 tables, 11 fields, 6 views, 5 mapped records, 14 ordinary cells, and 3 attachments.
- Field coverage: text, number, datetime, select, user, link, and attachment.
- Structure mismatches: 0; value mismatches: 0; attachment mismatches: 0.
- In-memory negative probes derived from the live target proved that a target-only ordinary value and a target-only attachment field both produce mismatches.

## Case 2 — current large paginated Base

- The source and target were recaptured live with the 1.0.1 capture code, not reused only as old manifests.
- Source: stable double read; target: live single read.
- Coverage: 10 tables, 2,579 mapped records, 55,379 ordinary cells, and 2,411 attachments.
- Structure mismatches: 0; value mismatches: 0; attachment mismatches: 0.
- The retained qualification metadata for this same case records 232 fields and 60 views.

## Case 3 — multiple and duplicate-stem attachments

- On the authorized disposable target, 3 files were removed from 2 attachment cells and then restored.
- Initial regenerated plan: 2 cells / 3 files.
- The first job uploaded two visible files with the same `same.svg` filename in one cell through one repeated-file operation.
- A previously qualified display derivative remains the representation evidence: source WebP rendered/decrypted as detected PNG with safe hash, byte-count, and dimension metadata; original-binary equality is not claimed.
- Final attachment mismatches: 0.

## Case 4 — source drift and interrupted recovery

- A controlled mutation occurred between the two source reads.
- `SourceChanged` was raised; the value was restored to `stable`; the following source double read was stable.
- After applying the first attachment job, execution was intentionally stopped.
- Fresh target evidence reduced the remaining plan from 2 cells / 3 files to 1 cell / 1 file.
- The runner uploaded only the remaining file and reached `COMPLETE`.
- Final report: 5 records and 14 ordinary cells verified; all mismatch lists empty.

## Boundaries and retained artifacts

- Workflows, dashboards, forms, advanced permissions, comments, sharing, and automations remain outside the replica contract.
- CDP fallback qualification covers PNG, WebP, and JPEG display derivatives only. Other attachment types require the official media path or separate proof.
- Display/content equality does not prove original extension, resolution, metadata, or byte-for-byte identity.
- The disposable Bases were restored to source-equivalent state.
- After explicit cleanup confirmation, decrypted files, upload staging, raw manifests, and record maps were deleted. Only the private `run.json` and `final-report.json` evidence files were retained with mode `0600`.
