# Douyin Scraping Strategy

## Access Ladder

1. Public browser session, no cookies.
   - Resolve `v.douyin.com` short links.
   - Read public page metadata and public network responses.
   - Capture video stream only when needed for first-scrape video analysis.
2. Logged-in Chrome fallback.
   - Use only after user consent.
   - Reuse one persistent browser context for the whole batch.
   - Use the dedicated Douyin browser profile: CDP `http://[::1]:9222`, user-data-dir `$HOME/Library/Application Support/Google/DouyinChrome`.
   - For repeated diagnostics, connect to an already-open Chrome over CDP and keep it open between links.
   - Use the same Chrome profile for login and scraping. A saved cookie file and a separate CDP `--user-data-dir` do not automatically share login state.
   - Keep batches small and delays human-paced.
3. Manual stop.
   - Stop on CAPTCHA, abnormal access, platform warning, login-risk, or repeated empty pages.

## Status Semantics

- blank/null and `准备抓取`: first scrape. Write `正文`, `点赞数`, `收藏数`, `抓取时间`, then set `抓取状态=保持抓取` on success.
- `保持抓取`: refresh engagement only. Write `点赞数`, `收藏数`, `抓取时间`; do not overwrite `正文`.
- `停止抓取`: do not process.
- `抓取异常`: do not process.

## Base Batch Pattern

1. Use `scripts/process-lark-douyin.mjs` for table-driven work.
2. Read explicit fields: `序号`, `平台`, `发布链接`, `列7`, `正文`, `点赞数`, `收藏数`, `抓取时间`, `抓取状态`.
3. Treat blank status as `准备抓取`.
4. Filter to `平台=抖音` and eligible status.
5. Send the whole batch to `scripts/scrape-douyin.py`; do not start a browser once per URL.
6. Re-read or dry-run before large runs when the view/filter changed.
7. If comment execution is requested, use one visible logged-in CDP browser with `--cdp-only --new-tab --comment`; post only rows where `抓取状态=保持抓取`, `生成评论` is non-empty, and `评论状态` is blank or `准备评论`.

Do not use the default Chrome profile or Weibo/Xiaohongshu ports for Douyin jobs.
In CDP mode, `--new-tab` reuses the stable worker tab named `codex-douyin-worker` through `window.name`; it should not create a fresh tab per process run.
The Base entrypoint must hold `/tmp/social-scraper-locks/douyin.lock` while running so another session cannot control the same Douyin browser concurrently.

## Failure Rules

- Public access failure alone is not enough to mark `抓取异常`.
- Confirmed deleted/non-existent/unavailable after the allowed fallback can be marked `抓取异常`.
- Login wall, empty shell page, or no metadata should be retained for later confirmation unless fallback was explicitly requested.
- Never set failed engagement counts to `0` unless the user explicitly chooses that policy.

## Failure Fuse

Use conservative automatic stops:

- Public batch: stop if 5 consecutive rows fail or if more than 40% of the batch fails.
- Logged-in Chrome fallback: default size 3-5; stop if 2 consecutive rows fail or if any platform warning appears.
- Confirmed deleted/unavailable rows should be marked `抓取异常` and excluded from automatic retry runs.
- Commenting is tracked separately with `评论状态`: blank by default, `准备评论` for selected rows, `取消评论`, `评论成功`, or `评论失败`. Douyin `准备评论` means the row has entered the comment queue and may be auto-commented when the logged-in browser path is enabled.
- A successful scrape can still have a failed comment attempt. In that case keep the engagement refresh, write `评论状态=评论失败`, and do not retry automatically until the user resets it to blank or `准备评论`.
- Production comment execution must use DOM selectors and post-submit verification, not screen coordinates.
- After a warning from 抖音, pause all logged-in browser scraping for at least 24-48 hours.
- Never run an outer shell loop that starts Chrome once per URL.
- When the user wants to watch or log in manually, keep one Chrome window open and navigate the same page instead of launching per URL.
- If using a visible CDP browser for the whole run, pass `--cdp-url` and `--cdp-only` so the Base entrypoint does not open a separate public browser first.

## Video Content Path

Use frame analysis for first-scrape videos:

1. Resolve the short link to the canonical `/video/<aweme_id>` page.
2. Match page/network metadata to that exact current `aweme_id`.
3. Download only the matched aweme's `video.play_addr` or `video.download_addr` stream URL.
4. If no current-aweme-bound stream URL is available, skip frame analysis for that row instead of using another visible/captured video URL.
5. Make a contact sheet:
   ```bash
   ffmpeg -hide_banner -loglevel error -y -i video.mp4 -vf "fps=1/3,scale=360:-1,tile=3x3" -frames:v 1 sheet.jpg
   ```
6. Ask MiniMax for visible subtitles, scenes, objects, products, people, places, and useful narrative details.
7. Append the result under `【视频内容解析】`.

Do not bind video analysis by comparing MiniMax output with the caption text. Douyin captions and video content can legitimately differ; the binding must come from current page URL/video id metadata.
