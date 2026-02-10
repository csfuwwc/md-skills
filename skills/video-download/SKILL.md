---
name: video-download
description: Download videos from Douyin (抖音), Xiaohongshu (小红书), and Bilibili (B站) to local disk. Use when the user shares a video link from these platforms, asks to download a video, or mentions v.douyin.com / xiaohongshu.com / xhslink.com / bilibili.com / b23.tv URLs.
---

# 抖音 / 小红书 / B站 视频下载

从分享链接下载视频到本地，无头浏览器后台执行，用户不可见。

## 下载流程

直接运行下载命令即可。B站视频如果未登录，脚本会**自动弹出浏览器**让用户登录，登录后自动继续下载。

```bash
python3 ~/.cursor/skills/video-download/scripts/download.py "<分享文本或链接>" [输出文件名.mp4]
```

**注意**：B站下载命令可能会阻塞等待用户在浏览器中登录。使用 Shell 工具时建议设置较长的超时（block_until_ms: 300000）或后台运行。

### Cursor 增强体验（可选）

在 Cursor 中可以用 AskQuestion 提供更好的交互体验：

1. 先检查登录状态：`python3 ... check-login bilibili`（退出码 2 = 需要登录）
2. 如果需要登录，后台启动：`python3 ... login bilibili --signal-file /tmp/video_dl_login_done`（block_until_ms: 0）
3. 用 AskQuestion 展示「已完成登录」/「跳过登录」按钮
4. 用户点确认后：`touch /tmp/video_dl_login_done`，等待登录脚本退出
5. 再执行下载命令

## 平台支持

脚本自动识别平台：

| 平台 | 支持的链接格式 | 需要登录 | 备注 |
|------|---------------|---------|------|
| 抖音 | `v.douyin.com/xxx` 短链、`www.douyin.com/video/xxx`、`modal_id=xxx` | 否 | 抓网络请求 |
| 小红书 | `xiaohongshu.com/discovery/item/xxx`、`explore/xxx`、`xhslink.com/xxx` | 否 | 抓网络请求 |
| B站 | `bilibili.com/video/BVxxx`、`b23.tv/xxx` 短链 | 推荐 | 解析 `__playinfo__`，需要 ffmpeg |

- 输出文件名可选，默认从视频标题生成
- 文件保存到 `~/Downloads/`
- 依赖：`playwright`、`ffmpeg`（B站需要）

## 登录管理

```bash
# 登录（打开可见浏览器）
python3 ~/.cursor/skills/video-download/scripts/download.py login bilibili

# 带信号文件的登录（Agent 交互模式用）
python3 ~/.cursor/skills/video-download/scripts/download.py login bilibili --signal-file /tmp/video_dl_login_done

# 检查登录状态
python3 ~/.cursor/skills/video-download/scripts/download.py check-login bilibili
```

Cookie 保存在 `~/.config/video-download/<平台>_cookies.json`，自动检测过期。

支持的平台: `bilibili` / `douyin` / `xiaohongshu`

## 依赖安装

```bash
pip3 install playwright && python3 -m playwright install chromium
brew install ffmpeg   # B站视频合并需要
```

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| SSL 证书错误 | 脚本已内置 `ssl._create_unverified_context` |
| 未捕获到视频地址 | 增加等待时间，或内容需要登录/是图文非视频 |
| curl/下载 403 | 检查 Referer 头是否匹配平台域名 |
| B站 ffmpeg 不存在 | `brew install ffmpeg` |
| B站画质低 | 执行 `login bilibili` 登录后重新下载 |
| CDN 地址过期 | 重新运行，URL 有几小时时效 |
| cookie 过期 | 重新执行 login 命令 |
