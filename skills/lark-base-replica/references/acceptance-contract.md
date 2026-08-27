# Acceptance contract

Do not collapse all results into a single `100%` claim. Verify and report each domain separately.

## Manifest and mapping shape

Use this minimal JSON shape for `scripts/replica_manifest.py`:

```json
{
  "manifest_version": 1,
  "role": "source",
  "base_token": "app...",
  "snapshot_digest": "sha256...",
  "stability": "double-read",
  "tables": [{
    "name": "Table name",
    "source_table_id": "tbl...",
    "target_table_id": "tbl...",
    "fields": [],
    "views": [],
    "records": [{
      "source_record_id": "rec...",
      "target_record_id": "rec...",
      "values": {"Field": "value"},
      "attachments": {
        "Images": [{
          "file_token": "...",
          "name": "source.webp",
          "output_path": "/tmp/token.png"
        }]
      }
    }]
  }]
}
```

The target snapshot uses the same semantic structure but records use `record_id`; it is accepted as live evidence with `stability: single-read`. Source acceptance requires `double-read` stability.

Keep mutable source-to-target IDs in a separate private record map:

```json
{
  "tables": {
    "tbl_source": {
      "target_table_id": "tbl_target",
      "records": {"rec_source": "rec_target"}
    }
  }
}
```

The decryption helper emits a separate safe attachment manifest. Before planning uploads, merge it by `file_token`; never copy `url`, `secret`, or `nonce` from the CDN mapping into the source manifest.

## Domain checks

### Structure

- Table count and names
- Field name, type, description, options, colors, number/date format, relationship configuration
- View name/type, visible-field order, filters, sorts, groups, card/timebar properties
- Preserve ordered arrays; ignore only JSON object-key order

### Ordinary data

- Record count per table
- Every writable ordinary cell for every mapped record
- Exact ordinary-value field-key set per record; target-only populated cells are mismatches
- Link-field table IDs and link-cell record IDs normalized from source IDs to exact target IDs through the private record map
- Exact mapped record-ID set; extra target records are mismatches
- Source revision stability during extraction
- Explicit list of read-only, formula, lookup, or inaccessible fields excluded from value equality

### Attachments

- Attachment-cell count
- Per-cell attachment count
- Filename-stem multiset equality
- Zero unknown target attachments
- Zero remaining upload-plan items
- For recovered display derivatives: detected format, decrypted byte count, SHA-256, and dimensions when the file format exposes them

Attachment acceptance proves display/content migration. It does not prove source filename extension, original resolution, byte-for-byte identity, or metadata preservation unless separately verified.

The CDP fallback currently qualifies only PNG, WebP, and JPEG display derivatives. Other file types require successful official-media recovery or must be reported as unverified.

### Platform objects

Report workflows, dashboards, forms, advanced permissions, comments, automations, and sharing independently. Mark each as verified, excluded, or inaccessible.

## Final report

Use this compact structure:

```text
Result: complete / partial / blocked
Target: <Base link>
Structure: <tables/fields/views checked, mismatch count>
Data: <records/cells checked, mismatch count>
Attachments: <files/cells checked, remaining count>
Excluded or inaccessible: <explicit list>
Representation limits: <original binary vs display derivative>
```
