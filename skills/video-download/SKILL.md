---
name: video-download
description: 从抖音、小红书、B站下载视频到本地。当用户分享视频链接、要求下载视频、或消息中包含 v.douyin.com / xiaohongshu.com / xhslink.com / bilibili.com / b23.tv 链接时触发。
---

# 国内视频平台下载

从抖音、小红书、B站下载视频到本地，后台无头浏览器执行，用户不可见。

## 执行步骤

### 1. 识别平台

从用户消息中提取视频链接。支持的格式：

| 平台 | 链接格式 | 画质 |
|------|---------|------|
| 抖音 | `v.douyin.com` 短链、`www.douyin.com/video/xxx`、`modal_id=xxx` 精选页 | 原画 |
| 小红书 | `xiaohongshu.com/discovery/item/xxx`、`explore/xxx`、`xhslink.com` 短链 | 原画 |
| B站 | `bilibili.com/video/BVxxx`、`b23.tv` 短链 | 登录 1080p / 未登录 480p |

### 2. B站登录检查（仅 B站需要）

B站未登录只能下载 480p。下载 B站视频前必须检查登录状态：

```bash
python3 ~/.cursor/skills/video-download/scripts/download.py check-login bilibili
```

- 退出码 `0`（`LOGIN_OK`）→ 跳到步骤 3
- 退出码 `2`（`LOGIN_REQUIRED`）→ 执行登录流程：

**登录流程：**

1. 后台启动登录浏览器（block_until_ms: 0）：
```bash
python3 ~/.cursor/skills/video-download/scripts/download.py login bilibili --signal-file /tmp/video_dl_login_done
```

2. 立即用 AskQuestion 向用户展示确认按钮：
   - 提示：「已打开 B站 登录页面，请在浏览器中完成登录，完成后点击确认。」
   - 选项 A：「已完成登录」
   - 选项 B：「跳过登录（低画质）」

3. 用户确认后：
   - 选 A → `touch /tmp/video_dl_login_done`，等待登录脚本退出，继续下载
   - 选 B → kill 登录进程，直接下载（480p）

4. 兜底：用户直接关闭浏览器窗口也会自动保存 cookie。

### 3. 下载视频

```bash
python3 ~/.cursor/skills/video-download/scripts/download.py "<用户发送的链接或文本>" [输出文件名.mp4]
```

- 脚本自动识别平台，无需指定
- 可以把用户的完整消息（含分享文本）直接作为第一个参数，脚本会自动提取链接
- 输出文件名可选，默认从视频标题生成
- 文件保存到 `~/Downloads/`

### 4. 其他登录命令

用户主动要求登录某平台时：

```bash
# 手动登录（打开可见浏览器，关闭窗口完成）
python3 ~/.cursor/skills/video-download/scripts/download.py login bilibili
python3 ~/.cursor/skills/video-download/scripts/download.py login douyin
python3 ~/.cursor/skills/video-download/scripts/download.py login xiaohongshu
```

Cookie 存储在 `~/.config/video-download/<平台>_cookies.json`，自动检测过期。

## 依赖

- `playwright`：无头浏览器（`pip3 install playwright && python3 -m playwright install chromium`）
- `ffmpeg`：B站音视频合并（`brew install ffmpeg`）

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| B站画质 480p | 需要登录：执行 `login bilibili` |
| 未捕获到视频地址 | 可能是图文内容而非视频，或需要登录 |
| ffmpeg 不存在 | `brew install ffmpeg` |
| cookie 过期 | 重新执行 `login` 命令 |
| CDN 地址过期 | 重新运行下载即可 |
