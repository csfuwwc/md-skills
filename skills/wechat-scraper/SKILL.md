---
name: wechat-scraper
description: Use the private Video-Picture-OSS-Auth WeChat gateway to fetch a public WeChat article, extract HTML/JSON/Markdown/text, identify its official account, list recent account articles, or complete QR-code login for history access. Trigger for 微信公众号文章抓取、公众号作者识别、最近文章链接、历史文章列表、公众号扫码登录和登录授权复用 requests.
---

# WeChat Official Account Scraper

Use the self-hosted gateway. Do not call a third-party public deployment when this service is available.

## Configure access

- Use `http://api-ai.modianinc.com:8080/wechat` as the default base URL.
- Send `WECHAT_API_KEY` as `X-API-Key`. Never print, log, or commit it.
- If the key exists only on `vps-boss`, execute requests there against `http://127.0.0.1:8080/wechat`; read the key from `/modian/Video-Picture-OSS-Auth/.env` without displaying it.
- Treat `auth-key`, `uuid`, QR images, cookies, and account data as secrets. Store reusable authorization with mode `0600` and delete temporary QR/session files after use.

Read [references/api.md](references/api.md) when constructing requests or interpreting responses.

## Choose the workflow

### Fetch one public article

Call `GET /api/public/v1/download` with the article `url` and requested `format` (`json`, `html`, `markdown`, or `text`). This does not require a WeChat login.

For a content request, return the requested representation or a faithful summary. Preserve the original title, `nick_name`, author, description, publication time, and source URL when available.

### List recent articles from the same account

1. Fetch the supplied article as JSON and read `nick_name`.
2. Ensure a reusable `auth-key` exists; otherwise complete the QR login workflow.
3. Call `GET /api/web/mp/searchbiz?keyword=<nick_name>&size=20` with `Cookie: auth-key=<value>`.
4. Select the result whose `nickname` exactly equals `nick_name`; do not choose a similar account.
5. Call `GET /api/web/mp/appmsgpublish?id=<fakeid>&begin=0&size=<limit>&keyword=` with the same cookie.
6. Parse `publish_page` as JSON. For every `publish_list` item, parse `publish_info`, then read its `appmsgex` articles.
7. Exclude deleted items, sort by `create_time` descending, and return the requested number of titles, dates, and links.

Do not depend on `searchbyurl`: its upstream account-name parser can fail on otherwise valid WeChat article URLs. Use the article JSON `nick_name` fallback above.

### Complete QR login

1. POST a unique session ID to `/api/web/login/session/<sid>` and retain the returned `uuid`.
2. Request `/api/web/login/getqrcode` with `Cookie: uuid=<uuid>`, save the image temporarily, and show it to the user.
3. Poll `/api/web/login/scan` with the same cookie. Ask the user to confirm in WeChat when required.
4. When `status` is `1`, POST `/api/web/login/bizlogin` with the same cookie.
5. Capture `auth-key` from the response `Set-Cookie` and store it securely for later history requests.

The upstream cookie is marked `Secure`, while the current service uses HTTP. Explicitly send the cookie header during this workflow instead of relying on an automatic HTTP cookie jar. QR lifetime is short; the successful login authorization is normally valid for about four days and is persisted by the service.

## Handle failures

- On `401`, verify only that `WECHAT_API_KEY` is configured; never reveal its value.
- On “未登录或登录已过期”, start QR login again.
- On an expired QR status, create a new session and image rather than reusing the old UUID.
- If exact account matching fails, report the parsed nickname and candidate names; do not guess.
- Do not change OSS or TikHub routes, deployment state, or WeChat account content while performing read-only scraping.
