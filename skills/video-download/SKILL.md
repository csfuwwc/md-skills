---
name: video-download
description: Download videos from Douyin (抖音), Xiaohongshu (小红书), and Bilibili (B站) to local disk. Use when the user shares a video link from these platforms, asks to download a video, or mentions v.douyin.com / xiaohongshu.com / xhslink.com / bilibili.com / b23.tv URLs.
---

# 国内视频平台下载

从抖音、小红书、B站下载视频到本地，后台自动完成，无需手动操作。

## 什么时候用

- 用户发了抖音分享链接想保存视频
- 想把小红书上看到的视频下载下来
- 保存 B站视频到本地离线观看
- 批量收藏视频素材
- 备份自己发布的内容

## 支持什么

| 平台 | 链接格式 | 画质 |
|------|---------|------|
| 抖音 | `v.douyin.com` 短链、完整视频链接、精选页链接 | 原画 |
| 小红书 | `xiaohongshu.com` 笔记链接、`xhslink.com` 短链 | 原画 |
| B站 | `bilibili.com/video/BVxxx`、`b23.tv` 短链 | 登录后 1080p，未登录 480p |

## 怎么用

### 基本下载

```text
下载这个视频: https://v.douyin.com/xxxxx
```

```text
帮我下载 https://www.bilibili.com/video/BV1xxxxx
```

### 小红书视频

```text
https://www.xiaohongshu.com/explore/xxxxx 下载
```

### 指定文件名

```text
下载这个视频，文件名叫 舞蹈教程.mp4: https://v.douyin.com/xxxxx
```

## 示例

**用户**: "https://www.bilibili.com/video/BV1ucFbzLEuG 下载"

**输出**:

```text
[1/5] 解析B站链接...
[2/5] BV号: BV1ucFbzLEuG, 启动无头浏览器...
  已加载 bilibili 登录态 (28 cookies)
[3/5] 视频: 1080x1438 avc1.640033
       音频: mp4a.40.2
[3/5] 下载视频流... 8.1MB
[4/5] 下载音频流... 0.6MB
[5/5] ffmpeg 合并音视频...

✓ 下载完成: ~/Downloads/绿幕转写实.mp4 (8.7MB)
```

## B站高清下载

B站未登录只能下载 480p。首次下载 B站视频时会自动引导登录：

1. 弹出浏览器窗口，打开 B站登录页
2. 你在浏览器里扫码或输密码登录
3. 登录完成后点击会话中的确认按钮（或直接关闭浏览器）
4. 自动保存登录态，后续下载直接使用，无需重复登录

如果 cookie 过期，会自动提示重新登录。

## 注意事项

- 所有视频保存到 `~/Downloads/` 目录
- 文件名自动从视频标题生成，也可以手动指定
- 抖音和小红书无需登录即可下载原画质量
- B站视频音频分离，下载后自动用 ffmpeg 合并
- 整个过程在后台无头浏览器中执行，用户不可见

## 常见问题

| 问题 | 怎么办 |
|------|--------|
| B站画质只有 480p | 需要登录，说「登录B站」即可 |
| 小红书下载失败 | 可能是图文笔记而非视频 |
| 提示 ffmpeg 不存在 | 运行 `brew install ffmpeg` |
| 视频地址过期 | 重新发链接下载即可 |
| cookie 过期了 | 说「重新登录B站」即可 |

---

<!-- Agent 实现细节（用户不可见） -->
<!-- 
脚本路径: ~/.cursor/skills/video-download/scripts/download.py

下载命令:
  python3 ~/.cursor/skills/video-download/scripts/download.py "<链接>" [文件名.mp4]

B站登录流程:
  1. 检查: python3 ... check-login bilibili（退出码 2 = 需要登录）
  2. 登录: python3 ... login bilibili --signal-file /tmp/video_dl_login_done（block_until_ms: 0 后台运行）
  3. 弹按钮: AskQuestion「已完成登录」/「跳过登录（低画质）」
  4. 确认后: touch /tmp/video_dl_login_done，等待登录脚本退出
  5. 兜底: 用户关浏览器窗口也会自动保存 cookie
  6. 继续下载

手动登录:
  python3 ... login bilibili
  python3 ... login douyin
  python3 ... login xiaohongshu

Cookie 存储: ~/.config/video-download/<platform>_cookies.json

依赖:
  pip3 install playwright && python3 -m playwright install chromium
  brew install ffmpeg
-->
