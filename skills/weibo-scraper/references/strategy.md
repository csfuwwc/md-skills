# Weibo Scraping Strategy

## Access

Static Weibo requests often return Visitor System or Forbidden. Prefer a live Chrome session over CDP:

- Connect with `--cdp-url http://127.0.0.1:9224`.
- Use the dedicated Weibo user-data-dir `$HOME/Library/Application Support/Google/SocialScraperProfiles/Weibo`.
- Use `--new-tab` so the user's existing tabs are not reused.
- In CDP mode, `--new-tab` reuses the stable worker tab named `codex-weibo-worker` through `window.name`; it should not create a fresh tab per process run.
- Do not inject external cookies into the live Chrome profile.
- Do not use the default Chrome profile or Douyin/Xiaohongshu ports for Weibo jobs.
- The Base entrypoint must hold `/tmp/social-scraper-locks/weibo.lock` while running so another session cannot control the same Weibo browser concurrently.

## Status-Driven Runs

Rows are controlled by `抓取状态`, not by whether `正文` is already filled.

- blank/null and `准备抓取`: first scrape. Write `正文`, `点赞数`, `收藏数`, `抓取时间`, then set `抓取状态=保持抓取`.
- `保持抓取`: refresh only `点赞数`, `收藏数`, `抓取时间`.
- `抓取异常`, `停止抓取`: do not process.
- Commenting is tracked separately with `评论状态`: blank by default, `准备评论` for selected rows, `取消评论`, `评论成功`, or `评论失败`. Weibo `准备评论` means the row has entered the comment queue and may be handled automatically when the logged-in browser path is available.
- Automatic commenting should only run when `抓取状态=保持抓取`, `生成评论` is non-empty, and `评论状态` is blank or `准备评论`.

## Parsing

Use page visible text and DOM:

1. Navigate to the Weibo post URL.
2. Wait for `微博正文` or visible post content.
3. Extract the post body from the area after the publish/source lines and before `播放视频` / `转发` / `评论` / `赞`.
4. Extract likes from visible action text. Bare `赞` means `0`.
5. Set collections to `0`, because public Weibo pages do not expose a reliable collection count.

## Video

For video rows, collect `video.currentSrc`, `video.src`, `source.src`, and response URLs containing `.mp4` or `.m3u8`. Prefer the current DOM video source. Download the video, make a contact sheet with ffmpeg, then run MiniMax vision.

Do not claim audio transcript accuracy unless an ASR tool processed the audio.
