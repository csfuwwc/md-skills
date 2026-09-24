---
name: tiktok-scraper
description: 从 TikTok 账号主页抓取账号指标、作品列表、互动数据以及视频或图文素材候选。用于 TikTok 账号上新监测和已有内容数据补齐；固定使用 MD-Browser TikTok 的 9225 CDP，不进入作品详情页。
---

# TikTok 账号主页抓取

使用 `scripts/scrape-profile.py` 连接已经启动且获准使用的 TikTok 浏览器：

```bash
python3 scripts/scrape-profile.py \
  --cdp-url http://127.0.0.1:9225 \
  --profile-url 'https://www.tiktok.com/@账号名' \
  --output /tmp/tiktok-profile.json
```

## 固定规则

- 账号指标从主页 rehydration 数据读取；作品和互动数据从 `/api/post/item_list/` 读取。
- Skill 返回平台提供的作品数据，不应用业务日期边界；发布时间范围由 Stagehand 等调用方决定。
- 视频保留主页列表的 `playAddr`、时长、尺寸和封面；图文保留 `imagePost.images` 原顺序。
- 每条作品必须校验作者 handle 与目标主页一致。
- 日常账号监测不进入作品详情页；临时素材 URL 应立即交给 `video-download` 下载并上传 OSS，不能当永久地址保存。
- 出现可见验证组件或访问告警时停止平台访问并报告证据，不清浏览器配置、不切节点。
- 本 Skill 只写本地 JSON，不直接写飞书。

## 输出

JSON 包含 `account`、`records`、`responses`、`stopReason`、`postApiComplete`。`postApiComplete=true` 表示已到列表末尾或已触达已知内容边界。
