---
name: tikhub-query
category: 内容抓取
short-description: 走公司内部计费网关查 TikTok 视频详情
description: Query TikTok video details through the company-internal metered TikHub HTTP gateway. Use when a user provides a TikTok video URL or asks for TikHub/TikTok data; the deterministic client reads the current lark-cli user's Feishu open_id and name and attaches them only for internal usage attribution.
---

# TikHub Query

Use `scripts/tikhub_query.py`; do not rebuild the HTTP request manually.

## Query

Run from this Skill directory:

```bash
python3 scripts/tikhub_query.py query \
  --url 'https://www.tiktok.com/@creator/video/7645609920322112798'
```

Use `--shop-region MX` only when the user supplies or requests a region override. Return the business JSON and usage receipt from the command.

The client automatically calls `lark-cli contact +get-user --as user --format json`, adds the current employee's `tenant_key`, `open_id`, name, and original TikTok URL to the query, and creates one idempotency key. On first use, the server adds the employee to the Feishu Base personnel table with a default monthly limit of 1000; later calls use the administrator-maintained monthly limit and active state. It does not use a personal gateway Token, Keychain, approval card, PKCE, or local pending state.

## Return result

- By default, lead with the five business metrics from the successful response: play, like, comment, collect, and share counts. Then include the gateway request ID and usage receipt concisely.
- Follow the user's requested fields, ordering, language, and format when specified. Reformat or select fields from the same response; never send another paid query only to change the presentation.
- Use only values present in the response. If a requested field is missing or null, say it is unavailable instead of guessing.
- Return the full business JSON only when the user explicitly asks for raw or complete JSON, or when it is necessary for diagnosis.

## Safety boundary

- Treat Feishu identity as internal usage attribution, not verified authorization. The company network/IP allowlist is the access boundary; an internal caller could spoof another employee's identity.
- Never print or request the VPS TikHub upstream Token. It remains server-side.
- Never retry a failed paid query automatically. Ask before sending another query because the first result may be uncertain.
- Never add a gateway override or arbitrary endpoint. The client is fixed to the company-internal HTTP gateway.
- Run `status` to verify the current Feishu identity or `doctor` to check local dependencies.
- If the identity is unavailable, follow the `lark-shared` user authorization flow and retry.

Read [references/protocol.md](references/protocol.md) only when diagnosing request or response behavior.
