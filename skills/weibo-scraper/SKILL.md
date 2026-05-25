---
name: weibo-scraper
description: Use when a user provides Weibo/微博 links, asks to fetch 微博 post text, likes, video visual content, or wants to fill a Lark Base table from 微博 links.
---

# Weibo Scraper

## Overview

Use this skill for 微博公开帖子链接抓取和飞书 Base 回填. Prefer a live Chrome CDP session because Weibo static endpoints often return Visitor System or Forbidden.

## Browser Profile

Use the dedicated Weibo browser profile and CDP endpoint:

- CDP URL: `http://127.0.0.1:9224`
- user-data-dir: `$HOME/Library/Application Support/Google/SocialScraperProfiles/Weibo`
- launcher: `~/.agents/social-browser-profiles/launch-social-chrome.sh weibo`

Do not use the default Chrome profile for Weibo scraping. Do not share this port/profile with Douyin or Xiaohongshu jobs.
The Base entrypoint uses a local platform lock at `/tmp/social-scraper-locks/weibo.lock`; do not run two Weibo jobs at the same time from different sessions.
In CDP mode, `--new-tab` means "use the reusable worker tab", not "create a fresh tab every run". The scraper finds a tab whose `window.name` is `codex-weibo-worker`; if none exists, it creates one and then keeps reusing it by replacing the URL.

## Workflow

For one-off diagnostics:

```bash
python3 ~/.agents/skills/weibo-scraper/scripts/scrape-weibo.py \
  --json --json-input --cdp-url http://127.0.0.1:9224 --new-tab
```

For Lark Base batch work:

```bash
node ~/.agents/skills/weibo-scraper/scripts/process-lark-weibo.mjs \
  --base-token <base_token> \
  --table-id <table_id> \
  --view-id <view_id> \
  --cdp-url http://127.0.0.1:9224 \
  --cdp-only \
  --new-tab \
  --batch-size 6
```

Batch mode writes each row back to Lark immediately after that row's scrape result is produced.

For logged-in comment execution:

```bash
node ~/.agents/skills/weibo-scraper/scripts/process-lark-weibo.mjs \
  --base-token <base_token> \
  --table-id <table_id> \
  --view-id <view_id> \
  --cdp-url http://127.0.0.1:9224 \
  --cdp-only \
  --new-tab \
  --worker-tab-name codex-weibo-worker \
  --comment \
  --batch-size 3
```

## Lark Status Rules

- blank/null: treat as `准备抓取`.
- `准备抓取`: first scrape. Fetch `正文`, `点赞数`, `收藏数`, and `抓取时间`. For videos, add visual-frame analysis to `正文`.
- `保持抓取`: refresh only `点赞数`, `收藏数`, and `抓取时间`. Do not overwrite `正文`.
- `抓取异常`: confirmed inaccessible, deleted, login/risk wall after allowed fallback, or unsafe to retry.
- `停止抓取`: manual or rule-based stop state for rows that no longer need engagement tracking.

On successful `准备抓取`, write body and engagement fields, then set `抓取状态=保持抓取`. On successful `保持抓取`, update only engagement fields and `抓取时间`. On confirmed terminal failure, set `抓取状态=抓取异常` and write `抓取时间`. `停止抓取` is not set automatically unless a separate stop-tracking rule is explicitly enabled.

## Comment Status Rules

Use `评论状态` as a separate operations queue:

- blank/null: default, not yet selected for commenting.
- `准备评论`: selected by threshold or manual review and waiting for comment execution.
- `取消评论`: manually decided not to comment.
- `评论成功`: comment has been posted.
- `评论失败`: a comment attempt failed and is not currently being retried.

The table does not need a `评论方式` field unless platform behavior becomes mixed. Keep `评论状态` blank by default. For Weibo, `准备评论` means the row has entered the comment queue and may be commented automatically from the logged-in browser. If automatic commenting is unavailable or risky, leave the row in `准备评论` for manual handling or write `评论失败` with a failure reason field if present.
Weibo comments can be posted automatically from the logged-in CDP browser when `抓取状态=保持抓取`, `生成评论` is non-empty, and `评论状态` is blank or `准备评论`. The current flow fills `textarea[placeholder="发布你的评论"]`, clicks the `评论` button, then verifies the comment text appears before writing `评论成功`.

## Output Rules

- `正文`: visible Weibo post text first. For videos, append `【视频内容解析】` when frame analysis succeeds.
- `点赞数`: visible Weibo like count. If the UI shows bare `赞` with no number, write `0`.
- `收藏数`: Weibo public posts do not expose a reliable collection count in the current page; write `0`.
- `抓取时间`: local datetime rounded to minutes, e.g. `YYYY-MM-DD HH:mm:00`.

## Safety

- Do not bypass CAPTCHAs, private content, paywalls, or account restrictions.
- Do not print cookies, tokens, localStorage, or profile secrets.
- Stop immediately on CAPTCHA, platform risk, or login-risk signals.
- Use one live Chrome session for a batch. Do not launch and close Chrome per URL.
- If using a visible CDP browser, use port `9224` and the Weibo profile only.

## References

- Read `references/strategy.md` before changing browser, status, video, or Base write behavior.
