# Release gates

Use these gates when promoting this Skill. A passing unit suite is necessary but does not prove live Feishu compatibility.

## Automated gates

- Manifest capture paginates serially and double-read source drift fails closed.
- Manifest fixtures cover current `data.tables`, `data.fields`, and columnar `record-list` envelopes, not only legacy `items` rows.
- Link-field fixtures prove source table/record IDs are normalized through the private source-to-target map without rewriting user IDs.
- Semantic comparison ignores JSON object-key order but preserves ordered arrays.
- Extra/missing target records, cells, and attachments are mismatches.
- Empty list-valued ordinary fields remain ordinary values unless their field schema is attachment.
- Attachment planning is idempotent across display-derivative extensions and preserves duplicate filename-stem multiplicity.
- Retrying the attachment phase after an interruption regenerates the plan from fresh target evidence and includes only missing files.
- Run-ledger transitions cannot skip acceptance phases; private artifacts are mode `0600`.
- Cleanup cannot escape the run directory; upload staging rejects symlink escapes.
- Evidence manifests must match the authorized target token; attachment sources must stay inside the run directory, match available hashes, and stop on the first failed upload job.
- Decrypted manifests remove CDN URL/AES fields and record fidelity metadata.
- Current CLI help must explicitly promise `stringArray`, repeated-file append, multiple attachments, and same-cell semantics before multi-file writes; accept both official phrasings `same attachment cell` and `one cell`.

## Live qualification matrix

Before labeling the release generally available, complete all four with source read-only and a disposable authorized target:

1. Small Base: text, numbers, dates, options, people/link fields where supported, two views.
2. Large paginated Base: more than 200 records and enough tables/fields/views to cross every page boundary.
3. Attachment Base: zero, one, and multiple images per cell; duplicate filename stems; at least one display derivative.
4. Change/recovery Base: mutate the source between double reads, interrupt an upload, re-read target, and prove only remaining files are planned.

For each case retain a redacted final report with domain counts, mismatches, exclusions, CLI version, and representation limits. Never retain signed URLs, access tokens, cookies, AES material, or decrypted assets in published fixtures.

## Promotion rule

- `rc`: automated gates pass, but any live case is missing or current CLI blocks a required capability.
- `stable`: all four live cases pass with zero mismatch in every claimed domain.
- Any platform regression returns the affected capability to blocked/partial until requalified.
