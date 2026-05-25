---
name: douyin-scraper
description: Use when a user provides Douyin/抖音 links, v.douyin.com short links, asks to fetch 抖音 video text, likes, collections/favorites, video visual content, or wants to fill a Lark Base table from 抖音 links.
---

# Douyin Scraper

## Overview

Use this skill for 抖音公开视频链接抓取和飞书 Base 回填. Default to public, non-logged-in access. Use a logged-in Chrome profile only as a low-frequency fallback after user consent.

## Browser Profile

Use the dedicated Douyin browser profile and CDP endpoint:

- CDP URL: `http://[::1]:9222`
- user-data-dir: `/Users/liyanpeng/Library/Application Support/Google/DouyinChrome`
- launcher: `/Users/liyanpeng/.agents/social-browser-profiles/launch-social-chrome.sh douyin`

Do not use the default Chrome profile for Douyin scraping or commenting. Do not share this port/profile with Xiaohongshu or Weibo jobs.

## Workflow

1. Extract canonical URLs from raw text, Markdown links, or Base cells.
2. For one-off diagnostics, run:
   ```bash
   python3 ~/.agents/skills/douyin-scraper/scripts/scrape-douyin.py --json < urls.txt
   ```
3. For Lark Base batch work, use the safe Base entrypoint:
   ```bash
   node ~/.agents/skills/douyin-scraper/scripts/process-lark-douyin.mjs \
     --base-token <base_token> \
     --table-id <table_id> \
     --view-id <view_id> \
     --batch-size 10
   ```
4. If public access fails and the user explicitly agrees to fallback, retry with a logged-in Chrome profile:
   ```bash
   node ~/.agents/skills/douyin-scraper/scripts/process-lark-douyin.mjs \
     --base-token <base_token> \
     --table-id <table_id> \
     --view-id <view_id> \
     --browser-confirm \
     --chrome-user-data-dir "$HOME/Library/Application Support/Google/DouyinChrome" \
     --batch-size 3
   ```

Do not wrap the scraper in a shell loop. Batch mode must reuse one browser context for the whole batch and should write each row back to Lark immediately after that row's scrape result is produced.
When `--browser-confirm` is used, still run public access first; retry only the failed rows with the logged-in Chrome profile.
For repeated visible-browser diagnostics or fallback, prefer a long-lived Chrome opened with remote debugging and pass `--cdp-url 'http://[::1]:9222'` plus `--cdp-only` when the user explicitly wants all rows to use that visible browser. Do not repeatedly open and close Chrome.

Important: login state belongs to the Chrome profile that is open. A cookie file saved by another helper or a different `--user-data-dir` is not the same as the visible CDP browser profile. When using `--cdp-url`, do not inject saved cookie files into that browser context; trust the live profile's own cookies. If a new CDP profile is used, the user may need to log in there once, then keep that browser open.

If direct navigation in the first tab triggers login friction but manual opening a link in a new tab works, use `--new-tab` with `--cdp-url`. This creates a dedicated tab inside the same live Chrome profile and leaves the user's existing login tab untouched.

In CDP mode, `--new-tab` means "use the reusable worker tab", not "create a fresh tab every run". The scraper finds a tab whose `window.name` is `codex-douyin-worker`; if none exists, it creates one and then keeps reusing it by replacing the URL. Use `--worker-tab-name <name>` only when intentionally running a separate isolated Douyin worker.

For logged-in comment execution, use the same long-lived CDP browser and add `--comment`. This posts only when all conditions are true: `抓取状态=保持抓取`, `生成评论` is non-empty, and `评论状态` is blank or `准备评论`. Never comment rows already marked `评论成功`, `取消评论`, or `评论失败`.

The Base entrypoint uses a local platform lock at `/tmp/social-scraper-locks/douyin.lock`; do not run two Douyin jobs at the same time from different sessions.

## Lark Status Rules

Use `抓取状态` as the control plane:

- blank/null: treat as `准备抓取`.
- `准备抓取`: first scrape. Fetch `正文`, `点赞数`, `收藏数`, and `抓取时间`. For videos, add visual-frame analysis to `正文`.
- `保持抓取`: refresh only `点赞数`, `收藏数`, and `抓取时间`. Do not fetch or overwrite `正文` by default.
- `抓取异常`: confirmed deleted, unavailable, non-existent, login-blocked after allowed fallback, or unsafe to retry.
- `停止抓取`: manual or rule-based stop state for rows that no longer need engagement tracking.

Default runs process rows whose `抓取状态` is blank, `准备抓取`, or `保持抓取`. On successful `准备抓取`, write body and engagement fields, then set `抓取状态=保持抓取`. On successful `保持抓取`, update only engagement fields and `抓取时间`. On confirmed terminal failure, set `抓取状态=抓取异常`, write `抓取时间`, and preserve existing useful values. `停止抓取` is not set automatically unless a separate stop-tracking rule is explicitly enabled.

## Comment Status Rules

Use `评论状态` as a separate operations queue:

- blank/null: default, not yet selected for commenting.
- `准备评论`: selected by threshold or manual review and waiting for comment execution.
- `取消评论`: manually decided not to comment.
- `评论成功`: comment has been posted.
- `评论失败`: a comment attempt failed and is not currently being retried.

The table does not need a `评论方式` field unless platform behavior becomes mixed. Keep `评论状态` blank by default; use `准备评论` only when a row has been selected for commenting. Douyin comments can be posted automatically from the logged-in CDP browser with:
```bash
node ~/.agents/skills/douyin-scraper/scripts/process-lark-douyin.mjs \
  --base-token <base_token> \
  --table-id <table_id> \
  --view-id <view_id> \
  --cdp-url 'http://[::1]:9222' \
  --cdp-only \
  --new-tab \
  --worker-tab-name codex-douyin-worker \
  --comment \
  --batch-size 3
```

Comment automation uses page DOM controls inside `#comment-input-container`, fills `.public-DraftEditor-content[contenteditable=true]`, clicks the publish control inside the same container, then verifies the comment text appears before writing `评论成功`. On failure it writes `评论失败`. Do not use coordinate clicks in production batches.

## Output Rules

- `正文`: original Douyin caption/title first. For videos, append:
  ```text
  【视频内容解析】
  ...
  ```
- `点赞数`: Douyin `digg_count` when available.
- `收藏数`: Douyin `collect_count` when available.
- When falling back to visible page metrics, video pages usually show `点赞数 / 评论数 / 收藏数 / 分享`; do not treat the second visible number as `收藏数` when three metrics are present.
- If the visible engagement UI shows only bare labels such as `赞` or `收藏` with no number, write `0` for that metric.
- `抓取时间`: use local datetime rounded to minutes, e.g. `YYYY-MM-DD HH:mm:00`.
- Missing engagement counts mean unavailable, not zero. Do not overwrite existing useful values with blanks.

## Video Analysis

For `准备抓取` video rows:

1. Resolve the short link to the real video page.
2. Capture public page/network metadata.
3. Extract the current `/video/<aweme_id>` from the resolved page URL and use only the matching aweme record's `video.play_addr`/`download_addr` stream URL.
4. Download the video to a task-specific local folder.
5. Use `ffmpeg` to create a contact sheet from representative frames.
6. Use MiniMax `mmx vision describe --region global` when available to describe visible captions, scene, product/person/place details, and narrative.

Do not use the first network-captured `douyinvod` response as the video source. In a reused browser page it can belong to the previous item, recommendation feed, or preloaded media. If a current-aweme-bound video URL is unavailable, skip video analysis and still write the caption/engagement values.

Do not claim audio transcript accuracy unless an ASR tool actually processed the audio.

## Safety

- Do not bypass CAPTCHAs, paywalls, private content, account restrictions, or platform access controls.
- Do not export or print cookies, tokens, localStorage, QR codes, or profile secrets.
- Stop immediately on CAPTCHA, access anomaly, platform warning, or account-risk signal.
- Keep logged-in fallback batches small, normally 3-5 rows.
- After a platform warning, pause logged-in browser scraping for at least 24-48 hours.

## References

- Read `references/strategy.md` before changing status rules, browser fallback, video parsing, or Base write semantics.
