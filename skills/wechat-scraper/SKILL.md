---
name: wechat-scraper
category: 内容抓取
short-description: 经自建网关抓公众号正文与历史文章列表
description: Use the private Video-Picture-OSS-Auth WeChat gateway to fetch one public WeChat official-account article as HTML, JSON, Markdown, or text, or list the latest articles from the same official account. Trigger for 微信公众号文章抓取、公众号内容提取、公众号作者识别、最近文章链接和历史文章列表 requests.
---

# WeChat Official Account Scraper

Use only the self-hosted gateway at `http://api-ai.modianinc.com:8080/wechat`. Do not call third-party deployments, localhost, SSH, the private upstream container, or WeChat endpoints directly.

The VPS network layer restricts callers by IP. Do not request, read, store, or send an API key, `auth-key`, Cookie, UUID, QR session, or other login credential. The gateway owns the shared official-account login.

Read [references/api.md](references/api.md) when constructing requests or interpreting responses.

## Fetch one public article

Call `GET /api/public/v1/download` with:

- `url`: the full `https://mp.weixin.qq.com/s/...` article URL.
- `format`: `markdown` by default, or `json`, `html`, or `text` when the user requests it.

For a content request, return the requested representation or a faithful summary. Preserve the original title, official-account name, author, description, publication time, and source URL when available.

If `format=json` returns HTTP 204 or an empty body, retry with `format=markdown`. Use `format=html` only when structured page metadata is required.

## List recent articles from the same account

Call `GET /api/v1/account/recent` with:

- `url`: any full article URL from the target official account.
- `limit`: the requested count from 1 to 20; default to 5.

Use the returned `account` and `articles` fields directly. Return each article's title, publication time, and URL; include summary or author when useful. The gateway performs exact account matching, deleted-item filtering, descending time ordering, response normalization, and shared-login injection.

Do not call `searchbiz`, `searchbyurl`, `appmsgpublish`, administrator-page, login, QR, or logout endpoints from this coworker-facing Skill.

## Handle failures

- On an IP access error or unreachable gateway, report that the caller's network is not in the VPS allowlist.
- On HTTP 503 mentioning the shared login, tell the user: `公众号共享登录态已过期，服务已通过飞书通知管理员扫码续期。` The gateway sends a deduplicated Feishu card with the administrator button. Do not open the administrator page, start a QR workflow, or ask the user for credentials.
- On HTTP 404 from the recent endpoint, report the parsed official-account name when present and do not guess a similar account.
- On an empty JSON article response, use the Markdown/HTML fallback above.
- Do not change OSS, TikHub, deployment state, administrator login state, or WeChat content while performing read-only scraping.
