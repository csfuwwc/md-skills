---
name: video-download
description: Download videos from Douyin (抖音), Xiaohongshu (小红书), and Bilibili (B站) to local disk. Use when the user shares a video link from these platforms, asks to download a video, or mentions v.douyin.com / xiaohongshu.com / xhslink.com / bilibili.com / b23.tv URLs.
---

# 抖音 / 小红书 / B站 视频下载

从分享链接下载视频到本地，无头浏览器后台执行，用户不可见。

## 用法

```bash
python3 ~/.cursor/skills/video-download/scripts/download.py "<分享文本或链接>" [输出文件名.mp4]
```

脚本自动识别平台，支持：

| 平台 | 支持的链接格式 | 备注 |
|------|---------------|------|
| 抖音 | `v.douyin.com/xxx` 短链、`www.douyin.com/video/xxx` | 抓网络请求 |
| 小红书 | `xiaohongshu.com/discovery/item/xxx`、`explore/xxx`、`xhslink.com/xxx` | 抓网络请求 |
| B站 | `bilibili.com/video/BVxxx`、`b23.tv/xxx` 短链 | 解析 `__playinfo__`，需要 ffmpeg |

- 输出文件名可选，默认从视频标题生成
- 文件保存到 `~/Downloads/`
- 依赖：`playwright`、`ffmpeg`（B站需要）

## 依赖安装

如果依赖未安装，按需执行：

```bash
pip3 install playwright && python3 -m playwright install chromium
brew install ffmpeg   # B站视频合并需要
```

## B站特殊说明

B站使用 DASH 格式（视频+音频分离），脚本自动：
1. 从 `window.__playinfo__` 提取最高画质视频流和音频流 URL
2. 分别下载到 `/tmp/bili_dl/`
3. 用 `ffmpeg -c:v copy -c:a copy` 无损合并
4. 清理临时文件

未登录状态下最高获取 480p，登录后可获取更高画质。

## 手动方式（备用）

当脚本失败时：

1. 解析短链重定向: `curl -sL -o /dev/null -w '%{url_effective}' "<短链接>"`
2. Playwright MCP `browser_navigate` 访问视频页
3. `browser_wait_for` 等待 5-8 秒
4. 抖音/小红书: `browser_network_requests` 导出日志，过滤 CDN 关键词
5. B站: `browser_evaluate` 执行 `window.__playinfo__` 获取视频流 URL
6. 下载时必须带对应平台的 `Referer` 头

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| SSL 证书错误 | 脚本已内置 `ssl._create_unverified_context` |
| 未捕获到视频地址 | 增加等待时间，或内容需要登录/是图文非视频 |
| curl/下载 403 | 检查 Referer 头是否匹配平台域名 |
| B站 ffmpeg 不存在 | `brew install ffmpeg` |
| B站画质低 | 未登录限制，目前脚本不支持登录态 |
| CDN 地址过期 | 重新运行，URL 有几小时时效 |
