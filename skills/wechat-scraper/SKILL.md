---
name: wechat-scraper
description: Fetch and archive one public WeChat official-account article with direct static HTML parsing, private-gateway fallback, and final browser rendering, or list the latest articles through the same gateway. Trigger for 微信公众号文章抓取、公众号内容提取、公众号作者识别、最近文章链接、历史文章列表、微信文章 HTML/Markdown/纯文本和离线归档 requests.
---

# WeChat Official Account Scraper

For one public article, use this fixed order: bundled static parser, self-hosted gateway fallback, then Playwright final fallback. Stop immediately after the first semantically complete result. Use the gateway at `http://api-ai.modianinc.com:8080/wechat` as the primary path only for recent-account history. Do not call third-party deployments, SSH, the private upstream container, or raw WeChat login/history endpoints.

The VPS network layer restricts callers by IP. Do not request, read, store, or send an API key, `auth-key`, Cookie, UUID, QR session, or other login credential. The gateway owns the shared official-account login.

Read [references/api.md](references/api.md) when using the gateway or interpreting its responses.
Read [references/rebuild.md](references/rebuild.md) only when the user asks how the gateway works, needs to rebuild or recover it, or explicitly authorizes service-side diagnosis after a gateway failure. Treat the documented hosts and versions as replaceable baselines, re-check repositories before rebuilding, and never infer permission to access or change the VPS.

## Fetch one public article

Use this decision sequence:

```text
static parser
  -> complete body: stop
  -> failed/incomplete: private gateway
       -> complete body: stop
       -> failed/incomplete/unreachable: Playwright
            -> complete body: stop
            -> failed: report unsupported and retain available raw HTML
```

Do not call the gateway or launch a browser after static extraction succeeds. This preserves independence from the VPS and avoids unnecessary network, CPU, memory, and latency.

### 1. Static parser

Run:

```bash
python3 scripts/fetch_article.py \
  --url 'https://mp.weixin.qq.com/s/...' \
  --output-dir '<temporary-or-requested-output-directory>'
```

Install `beautifulsoup4` when the script reports that it is missing. If Framework Python reports `CERTIFICATE_VERIFY_FAILED`, install `certifi`; never disable TLS verification. The script uses Python's standard-library HTTP client, validates the WeChat article URL, sends a desktop User-Agent with WeChat Referer/Origin, preserves `raw.html`, and writes:

```text
raw.html
content.html
content.txt
metadata.json
assets/
```

It handles two static page forms in this order:

1. A non-empty `#js_content` traditional article (`fetch_method=static-dom`).
2. An async/text article whose body is in `window.cgiDataNew.content_noencode` or `text_page_info.content` (`fetch_method=static-cgiDataNew`), including `is_async=1`, `page_type=2`, or `item_show_type=10`.

Do not treat HTTP 200 or a present `#js_article` as sufficient. Confirm that `content.txt` contains the article body and `metadata.json` has the source URL. When those checks pass, return the static result and do not run either fallback.

Use `--input-html <raw.html>` to reparse a saved response without network access. Use `--skip-assets` only when the user does not need offline images or during parser diagnosis.

### 2. Private gateway fallback

Use the gateway only when the static request fails, the script exits with code 2, or semantic validation shows incomplete content. Request:

1. `format=json`
2. `format=markdown` when JSON is HTTP 204 or empty
3. `format=html` when earlier formats are incomplete or structured HTML/assets are required

Validate body content after every response. HTTP 200, a non-empty response, CSS-only Markdown, an empty `#js_article`, duplicated navigation UI, or metadata without body text is not success. Stop when a representation contains the complete article body. For full offline archival, prefer a successful HTML response and run it through the same DOM cleaning and asset-localization rules.

If the gateway is unreachable, denied by the VPS IP allowlist, or returns only incomplete formats, continue to Playwright for a single public article. Gateway failure is terminal only for history features that require the shared login.

### 3. Playwright final fallback

Use Playwright only after both the static parser and gateway fallback fail:

1. Open the same public article URL with a desktop User-Agent.
2. Wait for `#js_content`.
3. Scroll to the bottom to trigger lazy loading.
4. Save the rendered HTML.
5. Parse it with the same DOM logic.
6. Remove title duplication, `#js_article_bottom_bar`, reward/赞赏 UI, QR placeholders, location, publication footer, scripts, and styles.

Do not build anti-fingerprint or anti-detection behavior.

For a content request, return the requested representation or a faithful summary. Preserve the original title, official-account name, author, description, publication time, source URL, and fetch method when available. Keep temporary validation artifacts outside Obsidian unless the user asks to archive the article.

## List recent articles from the same account

Call `GET /api/v1/account/recent` with:

- `url`: any full article URL from the target official account.
- `limit`: the requested count from 1 to 20; default to 5.

Use the returned `account` and `articles` fields directly. Return each article's title, publication time, and URL; include summary or author when useful. The gateway performs exact account matching, deleted-item filtering, descending time ordering, response normalization, and shared-login injection.

Do not call `searchbiz`, `searchbyurl`, `appmsgpublish`, administrator-page, login, QR, or logout endpoints from this coworker-facing Skill.

## Handle failures

- On an IP access error or unreachable gateway during single-article retrieval, continue to Playwright. For recent/history retrieval, report that the caller's network is not in the VPS allowlist.
- On HTTP 503 mentioning the shared login, tell the user: `公众号共享登录态已过期，服务已通过飞书通知管理员扫码续期。` The gateway sends a deduplicated Feishu card with the administrator button. Do not open the administrator page, start a QR workflow, or ask the user for credentials.
- On HTTP 404 from the recent endpoint, report the parsed official-account name when present and do not guess a similar account.
- When static single-article parsing has no body, preserve `raw.html` and try the private gateway before Playwright.
- When the gateway returns empty JSON, CSS-only Markdown, or an empty `#js_article`, treat it as incomplete and continue to Playwright.
- Report an unsupported page form only after static, gateway, and Playwright paths all fail semantic body validation.
- Do not change OSS, TikHub, deployment state, administrator login state, or WeChat content while performing read-only scraping.
