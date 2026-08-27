# Capability ladder

Choose the lightest path that covers the requested acceptance domains. Recheck live behavior on every run.

| Level | Path | Use when | Stop condition |
|---|---|---|---|
| 1 | `lark-cli base +base-copy` | Source permits an official copy | Copy is forbidden, incomplete, or excludes required objects |
| 2 | `lark-cli base +table-list/+field-list/+view-*/+record-*` | User identity can read source structure/data | API returns a real permission error; do not loop retries |
| 3 | Browser-visible snapshot | Content is rendered to the current signed-in user but absent from official responses | Requested content is not visible or authentication is missing |
| 4 | Origin-scoped CDP attachment adapter | Visible attachment tokens need their signed CDN mapping | Token is not tied to a visible record, mapping is denied, or origin changes |

## Required probes

1. Run `lark-cli auth status` outside an environment that blocks the system keychain.
2. Resolve Wiki URLs to the real Base token when possible.
3. Compare source table/field/view/record counts before creating anything.
4. Run `lark-cli base +record-upload-attachment --help` before attachment writes.
5. Require help text to state that repeated `--file` values append multiple attachments in one cell.

If the installed CLI lacks the required capability, do not update it silently. Explain why the capability is required and obtain approval for an update or an isolated compatible invocation.

## Selection rules

- Prefer official shortcuts over registered APIs and raw APIs.
- Do not call raw Base OpenAPI paths when the `lark-base` Skill provides the operation.
- Browser/CDP is an attachment recovery adapter, not the default Base reader.
- Never infer inaccessible permission settings, workflows, dashboards, or forms from visible structure.
