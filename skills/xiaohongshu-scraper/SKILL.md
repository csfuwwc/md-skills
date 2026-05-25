---
name: xiaohongshu-scraper
description: Use when a user provides Xiaohongshu/XHS/xhslink URLs, asks to fetch 小红书 note or video content, likes, saves/collections, comments, publish metadata, or wants to fill a spreadsheet/Base from 小红书 links.
---

# Xiaohongshu Scraper

## Overview

Use this skill for 小红书笔记链接抓取和表格回填. Prefer reliable, low-frequency access patterns and preserve user intent: do not invent engagement numbers when the public page hides them.

## Browser Profile

Use the dedicated Xiaohongshu browser profile and CDP endpoint when a logged-in visible browser is explicitly needed:

- CDP URL: `http://127.0.0.1:9223`
- user-data-dir: `/Users/liyanpeng/Library/Application Support/Google/SocialScraperProfiles/Xiaohongshu`
- launcher: `/Users/liyanpeng/.agents/social-browser-profiles/launch-social-chrome.sh xhs`

Do not use the default Chrome profile for Xiaohongshu scraping. Do not share this port/profile with Douyin or Weibo jobs.
The Base entrypoint uses a local platform lock at `/tmp/social-scraper-locks/xiaohongshu.lock`; do not run two Xiaohongshu jobs at the same time from different sessions.

## Workflow

1. Extract canonical URLs from raw text, Markdown links, or Base cells.
2. Run the static scraper first:
   ```bash
   node ~/.agents/skills/xiaohongshu-scraper/scripts/scrape-xhs.mjs --json --delay-ms 6000 < urls.txt
   ```
3. For Lark Base batch work, use the safe Base entrypoint instead of shell loops:
   ```bash
   node ~/.agents/skills/xiaohongshu-scraper/scripts/process-lark-xhs.mjs \
     --base-token <base_token> \
     --table-id <table_id> \
     --view-id <view_id> \
     --batch-size 10
   ```
4. If a URL returns only `小红书`, `404`, or `当前内容无法展示`, retry with a real Chrome profile only when the user agrees:
   ```bash
   node ~/.agents/skills/xiaohongshu-scraper/scripts/process-lark-xhs.mjs \
     --base-token <base_token> \
     --table-id <table_id> \
     --view-id <view_id> \
     --browser-confirm \
     --chrome-user-data-dir "$HOME/Library/Application Support/Google/SocialScraperProfiles/Xiaohongshu" \
     --batch-size 3
   ```
5. For Lark Base updates, read the table fields first. Default runs process records whose `抓取状态` is blank, `准备抓取`, or `保持抓取`.
6. Write only storage fields such as `正文`, `点赞数`, `收藏数`, `抓取时间`, and confirmed terminal `抓取状态`. Use `lark-base` for Base commands.
7. Process in very small batches. Default: 3-5 records when using a logged-in browser, 10 records only for static H5. Stop when failures cluster.

Do not wrap `scrape-xhs.mjs --browser` in a shell loop for Base work. It is a lower-level scraper; use `process-lark-xhs.mjs` so status filtering, failure fuses, and Base writes stay consistent.

## Lark Status Rules

Use `抓取状态` as the control plane:

- blank/null: treat as `准备抓取`.
- `准备抓取`: new or newly appended row, eligible for first scraping. Fetch `正文`, `点赞数`, `收藏数`, and `抓取时间`.
- `保持抓取`: first scrape succeeded and data has been written; refresh only `点赞数`, `收藏数`, and `抓取时间`. Do not fetch or overwrite `正文` by default.
- `抓取异常`: confirmed inaccessible, app-only, login-wall, 404, repeated no-note-state, or platform warning risk. Do not retry automatically.
- `停止抓取`: manual or rule-based stop state for rows that no longer need engagement tracking.

Default runs scrape rows whose `抓取状态` is blank, `准备抓取`, or `保持抓取`. Treat blank as `准备抓取`. When a `准备抓取` row succeeds, write the scraped body and engagement fields, then set `抓取状态` to `保持抓取`. When a `保持抓取` row succeeds, update only engagement fields and `抓取时间`; keep `正文` and `抓取状态` unchanged. When a row is confirmed failed after the allowed fallback path, set `抓取状态` to `抓取异常`, write `抓取时间`, and preserve existing useful values.

## Comment Status Rules

Use `评论状态` as a separate operations queue. Keep it blank by default. The scraper may set `准备评论` only when a configured engagement threshold is reached or the user explicitly asks to queue rows for manual commenting; it must not publish Xiaohongshu comments automatically.

- blank/null: default, not yet selected for commenting.
- `准备评论`: selected by threshold or manual review and waiting for human commenting on Xiaohongshu.
- `取消评论`: manually decided not to comment.
- `评论成功`: human comment has been posted.
- `评论失败`: a comment attempt failed and is not currently being retried.

For now, Xiaohongshu commenting is all manual. The skill can help surface candidates by writing `评论状态=准备评论`, but comment publishing and final status changes are handled by the user. `准备评论` on Xiaohongshu means "ready for a human to comment", not "auto-comment now".

## Video Notes

When the row is marked `视频` or the note state contains video streams:

1. Download the video from the note's resolved stream URL when available, or use the local `video-download` skill if the stream URL is not directly exposed.
2. Extract representative frames with ffmpeg:
   ```bash
   ffmpeg -hide_banner -loglevel error -i video.mp4 -vf "fps=1/2,scale=720:-1" frames/frame_%03d.jpg
   ```
3. If MiniMax is configured, analyze the clearest frames with `mmx vision describe`:
   ```bash
   mmx vision describe --region global --image frames/frame_001.jpg --prompt "请提取这帧里的字幕、画面主体和对理解小红书视频正文有用的信息。"
   ```
4. Combine title, original desc, visible captions, and visual summaries into `正文`. Clearly mark inferred video content as `【视频内容解析】`.

MiniMax requires local authentication (`MINIMAX_API_KEY` or `mmx auth login`). If unavailable, fall back to manual frame review and say so. Video rows are higher risk and slower; process fewer per batch.

## Output Rules

- `正文`: title + newline + desc when both exist. Write this only for `准备抓取` rows unless the user explicitly requests body reprocessing.
- For videos, append a concise `【视频内容解析】` section when frame/video evidence is available.
- `点赞数` / `收藏数`: refresh for both `准备抓取` and `保持抓取` rows. Leave unavailable values unchanged/null unless the user explicitly asks to treat hidden values as `0`.
- `抓取时间`: use the user's current local datetime rounded to minutes, e.g. `YYYY-MM-DD HH:mm:00`, when the Base field supports time.
- `抓取状态`: write `保持抓取` only after a successful `准备抓取` first scrape. Keep `保持抓取` unchanged during engagement refresh. Write `抓取异常` only after an access failure is confirmed and no automatic retry should happen. Never write `停止抓取` automatically unless a separate stop-tracking rule is explicitly enabled.
- `评论状态`: blank by default; write `准备评论` only when an engagement threshold or explicit user instruction selects the row for commenting. Xiaohongshu `准备评论` means a human should comment.
- Preserve failed rows and report why they failed; do not overwrite useful existing values with blanks.

## Safety And Access

- Do not bypass CAPTCHAs, paywalls, private content, account restrictions, or platform access controls.
- Do not export or print cookies, tokens, localStorage, QR codes, or profile secrets.
- Default to non-logged-in static/H5 scraping. Use the user's own logged-in Chrome profile only as a fallback after consent. Keep rate low and human-paced.
- Do not repeatedly test rows already confirmed as inaccessible. Mark them `抓取异常`.
- Browser mode must reuse one browser session for a batch; do not launch and close Chrome for each URL.
- If using a visible CDP browser, use port `9223` and the Xiaohongshu profile only.
- Stop immediately after a platform warning or CAPTCHA/login-risk signal.
- Do not rotate IPs or use third-party proxies unless the user explicitly provides a compliant, owned proxy and the task is permitted.

## References

- Read `references/strategy.md` before changing crawl behavior, retry policy, browser profile usage, or Lark Base write semantics.
