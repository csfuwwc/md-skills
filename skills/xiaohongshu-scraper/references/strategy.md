# Xiaohongshu Scraping Strategy

## Access Ladder

1. Static H5 fetch with mobile UA.
   - Works for many `xhslink.com`, `xiaohongshu.com/discovery/item/...`, and share URLs.
   - Parse `window.__INITIAL_STATE__`; it is a JavaScript object literal, not strict JSON.
2. Browser render with installed Chrome.
   - Use when static fetch returns no note state.
   - Prefer persistent user data only after user consent.
   - Use the dedicated Xiaohongshu profile when a live browser is needed: CDP `http://127.0.0.1:9223`, user-data-dir `/Users/liyanpeng/Library/Application Support/Google/SocialScraperProfiles/Xiaohongshu`.
   - Use human-paced delays: 5-10 seconds between notes, longer after failures.
3. Manual/user-assisted path.
   - If 小红书 returns `当前内容无法展示`, login wall, 404, or app-only content, stop and report the row.
   - After confirmation, set `抓取状态=抓取异常`; do not continue retry loops.

## Status-Driven Runs

Every Base table used for scraping should contain `抓取状态`.

Rows with blank `抓取状态`, `抓取状态=准备抓取`, or `抓取状态=保持抓取` are eligible for default runs. Treat blank as `准备抓取`, and treat the status as a queue:

- blank/null: same as `准备抓取`.
- `准备抓取`: new or newly appended row; run the first scrape for body plus engagement.
- `保持抓取`: first scrape succeeded and data has been written; refresh only engagement metrics while waiting for manual review.
- `抓取异常`: confirmed inaccessible or unsafe to retry.
- `停止抓取`: manual or rule-based final state, excluded from all future scraping.

Before scraping:

1. Read `序号`, `发布链接`, `列7`, `正文`, `点赞数`, `收藏数`, `抓取时间`, `抓取状态`.
2. Filter to blank `抓取状态`, `抓取状态=准备抓取`, or `抓取状态=保持抓取`.
3. For `准备抓取`, scrape `正文`, `点赞数`, `收藏数`, and `抓取时间`. For `保持抓取`, scrape only `点赞数`, `收藏数`, and `抓取时间`; do not overwrite `正文`.
4. Stop the run when non-eligible rows dominate or when platform risk signals appear.

After scraping:

- `准备抓取` success: write `正文`, `点赞数`, `收藏数`, `抓取时间`, then set `抓取状态=保持抓取`.
- `保持抓取` success: write only `点赞数`, `收藏数`, `抓取时间`, and keep status unchanged.
- Confirmed inaccessible/app-only/login-wall/no-note-state after the allowed fallback path: set `抓取状态=抓取异常`.
- Commenting is tracked separately with `评论状态`: blank by default, `准备评论` for selected rows, `取消评论`, `评论成功`, or `评论失败`. Xiaohongshu comments are manual; the scraper may queue rows but must not publish comments. `准备评论` here means a human review/comment queue.
- Do not set failed counts to `0`; leave unavailable values blank/null.

## Data Semantics

`note.title` and `note.desc` are usually reliable when present.

`note.interactInfo.likedCount`, `niceCount`, and `collectedCount` are often empty on public H5 pages. Empty means unavailable, not zero. Only coerce to `0` when the user has explicitly chosen that policy.

Normalize counts:
- `"123"` -> `123`
- `"1.2万"` -> `12000`
- `""`, missing, non-numeric -> `null` by default

## Video Content Path

Video rows need a different body strategy from image-text notes. Public note metadata may contain a good title/desc, but the actual message often lives in on-screen subtitles and scenes.

Recommended path:

1. Resolve the final note URL and parse the note state.
2. Prefer the highest-quality playable stream URL in `video.media.stream` when exposed.
3. Download to a task-specific folder.
4. Use `ffprobe` to capture duration/resolution and `ffmpeg` to extract 1 frame every 2 seconds, plus a contact sheet for quick review.
5. Use MiniMax `mmx vision describe` on representative frames when `MINIMAX_API_KEY` is configured. Keep prompts focused on visible subtitles, scene description, products/people/places, and the narrative implied by frame sequence.
6. If no VLM is available, manually review contact sheets and say the content parsing is based on visible frames only.

Do not claim audio transcript accuracy unless an ASR tool or API actually processed the audio.

## Lark Base Batch Pattern

1. Use `scripts/process-lark-xhs.mjs` for table-driven batch work. Use raw `scrape-xhs.mjs` only for one-off diagnostics.
2. Use `lark-cli base +record-list` with the target view and explicit fields.
3. Map fields by real field names/ids from the returned `fields` list.
4. For each row:
   - require blank `抓取状态`, `抓取状态=准备抓取`, or `抓取状态=保持抓取`
   - extract `发布链接`
   - scrape note
   - update body only for `准备抓取`
   - update engagement metrics for both eligible statuses
   - set `抓取状态=保持抓取` only for successful `准备抓取`; set `抓取状态=抓取异常` only for confirmed terminal failures
5. Re-read the same 10 rows and summarize success/failure before continuing.

Use `+record-upsert --record-id` for row-specific updates. Use `+record-batch-update` only when the same patch applies to every row.

## Failure Fuse

Use conservative automatic stops:

- Static-only batch: stop if 5 consecutive rows fail or if more than 40% of the batch fails.
- Logged-in browser batch: default size 3-5; stop if 2 consecutive rows fail or if any platform warning appears.
- Confirmed app-only rows should be marked `抓取异常` and never included in automatic retry runs.
- After a warning from 小红书, pause all logged-in browser scraping for at least 24-48 hours.
- Never run an outer shell loop that starts Chrome once per URL. This pattern caused account warnings.

## Browser Profile Notes

For this workflow, do not use the default Chrome profile. Use the dedicated Xiaohongshu user-data-dir:

```bash
$HOME/Library/Application Support/Google/SocialScraperProfiles/Xiaohongshu
```

Launch it with `/Users/liyanpeng/.agents/social-browser-profiles/launch-social-chrome.sh xhs`, then connect via `http://127.0.0.1:9223`. When Chrome is already running, persistent context may fail or may conflict with the active profile. In that case, use the existing live CDP browser rather than launching another instance with the same user-data-dir.
The Base entrypoint must hold `/tmp/social-scraper-locks/xiaohongshu.lock` while running so another session cannot control the same Xiaohongshu browser concurrently.

Never print cookies, profile paths containing secrets, localStorage values, or request headers with credentials.

In browser batch mode, launch Chrome once and reuse the same context/page for all URLs in the batch. Do not wrap the scraper in an outer shell loop that starts Chrome once per URL.
