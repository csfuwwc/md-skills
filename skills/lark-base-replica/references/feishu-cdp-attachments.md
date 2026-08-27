# Feishu CDP attachment adapter

Use this adapter only for attachments the current signed-in user can visibly render and the official media path cannot download. Treat every endpoint and response shape here as unstable.

## Safety contract

- Use the Browser control Skill and its selected browser. Do not launch an unrelated profile.
- Keep the tab on the source Feishu origin before issuing CDP commands.
- Do not read cookies, local storage, profiles, passwords, or browser history.
- Build requests only from attachment tokens, fields, records, and revisions already captured from the visible Base.
- Store response mappings as `0600`; never print `url`, `secret`, or `nonce`.
- Delete mapping files and decrypted cache after successful target readback.

## Mapping request

The observed adapter uses an origin-scoped POST to:

```text
/space/api/box/file/cdn_url_v2/
```

The body shape is:

```json
{
  "files": [
    {"file_token": "<visible token>", "width": 720, "height": 720, "policy": "allow_up"}
  ],
  "extra": "{\"bitablePerm\":{\"tableId\":\"<source table>\",\"rev\":123,\"attachments\":{\"<field id>\":{\"<record id>\":[\"<visible token>\"]}}}}"
}
```

Execute the request through the tab's documented CDP `Runtime.evaluate` capability so the request remains origin-scoped. Do not export the signed-in session. Batch conservatively and verify that every returned `file_token` matches the request.

Expected response items may contain:

```json
{
  "file_token": "...",
  "url": "<temporary signed CDN URL>",
  "cipher_type": "1",
  "secret": "<base64 AES key>",
  "nonce": "<base64 nonce>",
  "permitted": true
}
```

Stop if `permitted` is false, the response is short, the cipher type is unknown, or the token does not match.

## Decryption and representation

For observed `cipher_type=1`, treat the CDN object as AES-256-GCM ciphertext with the final 16 bytes as the authentication tag. Use `scripts/decrypt_attachments.mjs`; do not log cryptographic material.

Detect the output type from decrypted bytes, not the source filename. Record SHA-256, decrypted byte count, and dimensions when supported. A source `.webp` attachment may produce a `.png` display derivative. Report this as display-equivalent content, not original-binary equivalence. The requested `720x720` mapping may downscale the original asset.

The bundled decryption helper recognizes PNG, WebP, and JPEG only. Do not route GIF, PDF, video, archives, raw SVG, or unknown binary formats through it; recover those through the official media path or report them as unverified.

## Upload invariants

- Match existing target attachments by filename stem so `.webp` → `.png` derivatives remain idempotent.
- Reject target files whose stems are absent from the source cell; they may be user changes.
- Pass every missing file in one cell through repeated `--file` flags in one append operation.
- Use paths inside the CLI working directory. Absolute paths and symlinks resolving outside the directory are rejected; use hardlinks or copies.
- Keep decrypted source files inside the private run directory and verify manifest SHA-256 metadata before staging when present.
- After any failure, re-read the target cell before retrying.
