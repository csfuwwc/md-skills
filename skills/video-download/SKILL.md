---
name: video-download
description: 从抖音、小红书、B站下载视频到本地。当用户分享视频链接、要求下载视频、或消息中包含 v.douyin.com / xiaohongshu.com / xhslink.com / bilibili.com / b23.tv 链接时触发。
---

# 抖音 / 小红书 / B站 视频下载

Download videos from Douyin, Xiaohongshu (RedNote), and Bilibili to local disk. Runs in a headless browser in the background, invisible to the user.

## Execution Steps

### 1. Identify Platform

Extract the video link from the user's message. Supported formats:

| Platform | Link Formats | Quality |
|----------|-------------|---------|
| Douyin (抖音) | `v.douyin.com` short links, `www.douyin.com/video/xxx`, `modal_id=xxx` | Original |
| Xiaohongshu (小红书) | `xiaohongshu.com/discovery/item/xxx`, `explore/xxx`, `xhslink.com` short links | Original |
| Bilibili (B站) | `bilibili.com/video/BVxxx`, `b23.tv` short links | 1080p logged in / 480p guest |

### 2. Bilibili Login Check (Bilibili only)

Bilibili limits guests to 480p. Before downloading Bilibili videos, check login status:

```bash
python3 ~/.cursor/skills/video-download/scripts/download.py check-login bilibili
```

- Exit code `0` (`LOGIN_OK`) → skip to step 3
- Exit code `2` (`LOGIN_REQUIRED`) → run login flow:

**Login flow:**

1. Launch login browser in background (block_until_ms: 0):
```bash
python3 ~/.cursor/skills/video-download/scripts/download.py login bilibili --signal-file /tmp/video_dl_login_done
```

2. Immediately show a confirmation button to the user via AskQuestion:
   - Prompt: "Bilibili login page is open. Please log in via the browser, then click confirm."
   - Option A: "Login completed"
   - Option B: "Skip login (low quality)"

3. After user confirms:
   - Option A → `touch /tmp/video_dl_login_done`, wait for login script to exit, then continue download
   - Option B → kill login process, download directly (480p)

4. Fallback: if the user closes the browser window directly, cookies are saved automatically.

### 3. Download Video

```bash
python3 ~/.cursor/skills/video-download/scripts/download.py "<link or share text from user>" [output_filename.mp4]
```

- The script auto-detects the platform, no need to specify
- The user's full message (including share text) can be passed directly as the first argument; the script extracts the link automatically
- Output filename is optional; defaults to the video title
- Files are saved to `~/Downloads/`

### 4. Manual Login Commands

When the user explicitly asks to log in to a platform:

```bash
# Opens a visible browser; close the window to finish
python3 ~/.cursor/skills/video-download/scripts/download.py login bilibili
python3 ~/.cursor/skills/video-download/scripts/download.py login douyin
python3 ~/.cursor/skills/video-download/scripts/download.py login xiaohongshu
```

Cookies are stored at `~/.config/video-download/<platform>_cookies.json` with automatic expiry detection.

## Dependencies

- `playwright`: headless browser (`pip3 install playwright && python3 -m playwright install chromium`)
- `ffmpeg`: Bilibili video/audio merging (`brew install ffmpeg`)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bilibili 480p only | Login required: run `login bilibili` |
| No video URL captured | Content may be image-only, or login is needed |
| ffmpeg not found | `brew install ffmpeg` |
| Cookie expired | Re-run the `login` command |
| CDN URL expired | Re-run the download |
