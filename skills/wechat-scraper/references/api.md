# Private WeChat gateway API

Base URL: `http://api-ai.modianinc.com:8080/wechat`

The VPS network layer restricts callers by IP. Do not attach application API keys, WeChat cookies, `auth-key`, or QR-session data.

## Fetch one public article

`GET /api/public/v1/download`

Query parameters:

- `url`: full `https://mp.weixin.qq.com/s/...` article URL.
- `format`: `json`, `html`, `markdown`, or `text`.

This operation does not require a WeChat login. Use it as the second-level single-article fallback only after the bundled static parser fails or returns incomplete content, and before launching Playwright.

A valid article can return:

- JSON: HTTP 204 with an empty body.
- Markdown: HTTP 200 containing only page CSS.
- HTML: HTTP 200 containing an empty `#js_article`.

Retrying formats is not proof of success. Validate that the response contains actual article body text. Stop at the first complete representation. If every format is incomplete or the gateway is unreachable, continue to Playwright. Async text articles may store the body only in `window.cgiDataNew.content_noencode` or `text_page_info.content`; the primary static parser handles that form.

## Fetch recent articles from the same official account

`GET /api/v1/account/recent`

Query parameters:

- `url`: any full article URL from the target official account.
- `limit`: integer from 1 to 20; defaults to 5.

Successful response:

```json
{
  "ok": true,
  "account": "公众号名称",
  "articles": [
    {
      "title": "文章标题",
      "url": "https://mp.weixin.qq.com/s/example",
      "summary": "摘要",
      "author": "作者",
      "create_time": 1785112345,
      "published_at": "2026-07-27T11:12:25+08:00"
    }
  ]
}
```

The gateway identifies the account, requires an exact nickname match, injects the VPS-owned shared login, filters deleted records, sorts newest first, and enforces the requested limit.

Relevant failures:

- `400`: invalid article URL or limit.
- `404`: exact official-account match not found.
- `503`: shared login missing or expired. The gateway sends the administrator a Feishu renewal card, deduplicated for 30 minutes; ordinary callers should wait for renewal and retry later.
- `502`: upstream WeChat service failed.

## Boundaries

The coworker-facing Skill must not call the administrator page or raw login, QR, search, history, or logout routes. The private `wechat-article-exporter` container must not publish a host port.

Direct access is permitted only for the public `https://mp.weixin.qq.com/s/...` article URL handled by the bundled single-article parser. It does not authorize direct access to login or history endpoints.
