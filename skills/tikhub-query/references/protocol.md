# Internal TikHub query protocol

The deterministic client calls only:

```text
POST http://api-ai.modianinc.com:8080/tikhub/search
```

The company network/IP allowlist is the access boundary. Feishu fields are trusted only as internal attribution labels.

Request body:

```json
{
  "caller": {
    "tenant_key": "current-user-tenant",
    "open_id": "current-user-open-id",
    "name": "current-user-name"
  },
  "platform": "tiktok",
  "type": "video_detail",
  "keyword": "7645609920322112798",
  "source_url": "https://www.tiktok.com/@blindboxbrando/video/7645609920322112798",
  "params": {"region": "US"}
}
```

Each invocation sends one `Idempotency-Key`. The client does not retry automatically and does not store a Token or local query state. The VPS supplies the upstream TikHub Token. Before a paid query, it resolves the employee by Feishu `open_id` in Base, creates a first-use row with a default monthly limit of 1000, and reads the administrator-maintained monthly limit and active state. Name changes update only the name field. SQLite performs idempotency and atomic monthly quota reservation, while success, failure, and rejection events are written to the Base usage table.

If the Feishu Base configuration cannot be read, the gateway returns `503` before calling TikHub. If the employee is disabled it returns `403`; if the monthly quota is exhausted it returns `429`.

`status` reads and prints only the current non-secret Feishu identity and fixed gateway. `doctor` reports Python, platform, lark-cli availability, and the fixed gateway.
