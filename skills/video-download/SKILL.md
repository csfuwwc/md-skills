---
name: video-download
description: Download videos from Douyin (抖音), Xiaohongshu (小红书), and Bilibili (B站) to local disk. Use when the user shares a video link from these platforms, asks to download a video, or mentions v.douyin.com / xiaohongshu.com / xhslink.com / bilibili.com / b23.tv URLs.
---

# Video Download Skill

## Overview

This skill enables automated video downloads from Chinese video platforms using headless browser automation. It handles platform detection, login management, and video extraction with proper quality settings.

## Quick Start

When a user requests video download, follow this decision tree:

1. **Identify platform from URL**
   - Douyin: `v.douyin.com/xxx`, `douyin.com/video/xxx`
   - Xiaohongshu: `xiaohongshu.com/discovery/item/xxx`, `xhslink.com/xxx`
   - Bilibili: `bilibili.com/video/BVxxx`, `b23.tv/xxx`

2. **Check dependencies**
   - First time use → Run `scripts/install_deps.sh` to install playwright and ffmpeg
   - Dependencies verified → Proceed to platform-specific workflow

3. **Execute platform workflow**
   - Douyin/Xiaohongshu → Direct download using `scripts/download.py`
   - Bilibili → Check login status first, then download

## Core Capabilities

### 1. Platform Support
- **Douyin (抖音)**: No login required, captures video URL from network requests
- **Xiaohongshu (小红书)**: No login required, captures video URL from network requests  
- **Bilibili (B站)**: Login recommended for HD quality, requires ffmpeg for video merging

### 2. Dependency Management
- **Auto-installation**: `scripts/install_deps.sh` handles all dependencies with China mirror optimization
- **Dependencies**: playwright (browser automation), ffmpeg (video processing for Bilibili)
- **Detection**: Script automatically checks for missing dependencies

### 3. Login Management
- **Cookie persistence**: Saves login state in `~/.config/video-download/<platform>_cookies.json`
- **Interactive login**: Opens visible browser for user authentication
- **Status checking**: Verifies login state before download
- **Supported platforms**: bilibili, douyin, xiaohongshu

### 4. Video Download
- **Automatic quality**: Best available quality (Bilibili HD requires login)
- **Title extraction**: Auto-generates filename from video title
- **Output location**: `~/Downloads/` directory
- **Format**: MP4 with proper codec settings

## Workflow Examples

### Example 1: Douyin/Xiaohongshu Direct Download
**User request**: "下载这个抖音视频 [v.douyin.com/xxx]"

**Workflow**:
1. Check dependencies installed using Shell command exit code
2. If missing → Execute `scripts/install_deps.sh` (block_until_ms: 120000)
3. Run `scripts/download.py` with video URL
4. Wait for download completion and report saved file path

### Example 2: Bilibili with Login Flow
**User request**: "下载这个B站视频 [bilibili.com/video/BVxxx]"

**Workflow**:
1. Check dependencies (playwright, ffmpeg)
2. Check login status using `scripts/download.py check-login bilibili`
3. If exit code 2 (LOGIN_REQUIRED):
   - Launch `scripts/download.py login bilibili --signal-file /tmp/video_dl_login_done` (block_until_ms: 0, run in background)
   - Immediately show AskQuestion to user:
     - Prompt: "已打开 B站 登录页面，请在浏览器中完成登录，完成后点击下方确认按钮。"
     - Option A: "已完成登录"
     - Option B: "跳过登录（使用低画质）"
   - If option A: Create signal file `touch /tmp/video_dl_login_done`, wait for login script exit
   - If option B: Kill login script process, proceed with low quality
4. Run `scripts/download.py` with video URL
5. Report completion and file location

### Example 3: First-Time User Setup
**User request**: "帮我下载小红书视频 [xhslink.com/xxx]"

**Workflow**:
1. Detect first use (no playwright/ffmpeg installed)
2. Inform user: "首次使用需要安装依赖（playwright 和 ffmpeg），约需 1-2 分钟"
3. Execute `scripts/install_deps.sh` (block_until_ms: 120000)
4. Monitor installation progress by reading terminal output
5. After success, proceed with download workflow

## Resource Guide

### scripts/

**Core script:**
- `download.py` - Main entry point for all download operations

**Available commands:**
- Download: Pass video URL as first argument, optional output filename as second
- Login: `login <platform>` - Opens browser for authentication
- Login with signal: `login <platform> --signal-file <path>` - For agent interaction mode
- Check status: `check-login <platform>` - Returns exit code 0 (logged in) or 2 (login required)

**Dependency installer:**
- `install_deps.sh` - One-click setup with China mirror optimization
  - Configures pip to use Tsinghua mirror
  - Sets Playwright download host to npmmirror
  - Installs playwright package
  - Installs Chromium browser
  - Installs ffmpeg via Homebrew

### Platform-Specific Notes

**Douyin (抖音)**:
- Accepts short links (v.douyin.com) or full URLs
- Extracts video from network HAR requests
- No login required
- Auto-detects modal_id from share text

**Xiaohongshu (小红书)**:
- Supports xiaohongshu.com and xhslink.com domains
- Captures video URL from page network requests
- No login required
- Works for both discovery and explore paths

**Bilibili (B站)**:
- Requires login for HD quality (1080p+), otherwise limited to 480p
- Uses `__playinfo__` page variable for video URL extraction
- Downloads separate audio/video streams and merges with ffmpeg
- Cookie expiration auto-detected

### Error Handling

| Exit Code | Meaning | Agent Action |
|-----------|---------|--------------|
| 0 | Success | Proceed to next step |
| 1 | General error | Report error message to user |
| 2 | Login required | Initiate login workflow |

| Common Issues | Auto-Resolution |
|---------------|-----------------|
| Missing dependencies | Run `scripts/install_deps.sh` |
| SSL certificate error | Script uses unverified SSL context |
| Video not captured | Content may require login or is image post |
| Low quality (Bilibili) | Prompt user to login for HD |
| Cookie expired | Re-run login command automatically |
| CDN URL expired | Retry download (URLs valid for few hours) |

## Technical Details

**Browser automation:**
- Uses Playwright with Chromium
- Headless mode (user-invisible)
- Network HAR capture for video URL extraction
- Cookie persistence across sessions

**Video processing:**
- Bilibili: Merges DASH audio/video streams using ffmpeg
- Douyin/Xiaohongshu: Direct MP4 download
- Proper HTTP headers (User-Agent, Referer) for CDN access

**File management:**
- Default output: `~/Downloads/<sanitized_title>.mp4`
- Title sanitization: Removes special chars, limits length
- Config directory: `~/.config/video-download/`

---

**Usage notes:**
- Script handles all platform detection automatically from URL
- Agent should monitor Shell command exit codes to handle errors
- Use AskQuestion tool for interactive login confirmation
- Set block_until_ms: 0 for login command to avoid blocking
- Dependency installation takes 1-2 minutes on first run
