# GA live qualification — 2026-08-27

Result: pass
CLI: lark-cli 1.0.90
Identity: user
Scope: authorized disposable source/target plus an earlier authorized large migration
Secrets retained: none in this report

## Case 1 — small complex-field Base

- Disposable source and target: 3 tables, 11 fields, 6 views, 5 records.
- Field coverage: text, number, datetime, select, user, link, attachment.
- Link schema table IDs and link-cell record IDs were normalized through the private mapping; user IDs were not rewritten.
- Final comparison: 5 records and 14 ordinary cells verified; structure mismatches 0, value mismatches 0.
- At least two grid views were created and exact visible-field order was read back.

## Case 2 — large paginated Base

- 10 tables, 232 fields, 60 views, 2,579 mapped records.
- 55,379 writable ordinary cells verified.
- 2,411 attachments across 2,045 attachment cells.
- Structure mismatches 0, value mismatches 0, attachment mismatches 0.
- Source snapshot was a stable double read.

## Case 3 — attachments

- Disposable matrix covered zero, one, and multiple files per cell.
- Duplicate filename stems were retained as a multiset: two visible files named same.svg in one cell.
- Controlled recovery target: 3 files across 2 non-empty attachment cells; final mismatches 0.
- Earlier authorized migration supplied display-derivative evidence: source WebP rendered/decrypted as detected PNG with safe size/hash/dimension metadata; original-binary equality was not claimed.

## Case 4 — change and recovery

- A controlled disposable source mutation occurred between double reads.
- Snapshot failed closed with SourceChanged; the source was restored and a later double read was stable.
- Initial attachment plan: 2 cells / 3 files.
- One job was applied, then execution intentionally stopped.
- Fresh target evidence regenerated the remaining plan to 1 cell / 1 file.
- Retry uploaded only the missing file; runner reached COMPLETE.
- Final comparison: structure, ordinary values, and attachments all had zero mismatches.

## Automated gates

- 18/18 unit tests passed.
- Skill quick validation passed.
- The active CLI help explicitly promises stringArray, repeated --file append, multiple attachments, one-cell semantics, and a maximum of 50 files.

## Exclusions and representation limits

- Workflows, dashboards, forms, advanced permissions, comments, sharing, and automations were not part of the replica contract.
- Attachment acceptance proves visible/display content and filename-stem multiplicity, not original resolution, original metadata, original extension, or byte-for-byte identity.
- Temporary Bases and private run artifacts were retained; cleanup requires separate explicit confirmation.

