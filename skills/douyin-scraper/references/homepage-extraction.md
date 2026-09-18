# 主页作品链接与数据提取

## 入口与范围

先从 MD-Browser MCP 读取并启动用户固定的抖音配置。复用返回的 CDP 地址、资料目录和已有登录，不另建身份，不修改端口，不主动置前窗口。新建标签页仍可能变为可见，后台运行需要在实际环境验收。

需要 Python 3.10+ 和 Playwright。由页面正常加载产生请求；不自行拼接签名接口，不绕过验证码或访问限制。使用平台锁，复用 `codex-douyin-worker`，不关闭用户的浏览器。

```bash
# DOUYIN_CDP_URL 来自本次 MD-Browser MCP 返回值。
python3 scripts/scrape-profile.py \
  --cdp-url "$DOUYIN_CDP_URL" \
  --profile-url 'https://www.douyin.com/user/<sec_uid>' \
  --output /absolute/task-folder/profile.json \
  --max-scrolls 12
```

仅补已有作品时，加 `--target-ids /absolute/task-folder/ids.json`；文件是平台 ID 字符串数组，不能包含 `douyin_` 前缀。脚本默认等待间隔 4500ms，可减少滚动上限做样本验证。输出本地报告，不自动写飞书、不下载媒体、不评论、不调用付费分析。

## 作品与来源校验

- 只处理 `/aweme/v1/web/aweme/post/` 且查询参数 `sec_user_id` 等于目标账号的响应。
- 每条还必须满足 `author.sec_uid` 精确匹配；作者缺失也跳过。不能从推荐内容或相邻 DOM 卡片补作者。
- 按 `aweme_id` 去重；统一生成 `/video/<id>` 或 `/note/<id>` 链接。不要使用标题作主键。
- 保存 `dataSource=profile_post_api`、`collectedAt`、原作者 ID、作品 ID。
- `statistics` 中点赞、评论、收藏、转发缺失时保留 null；真实数值 0 保留 0。不把未公开的播放量默认为 0。

## 封面：与主页展示一致

视频的静态展示封面选择：

1. 优先 `video.cover.url_list` 中首个可用 HTTPS 地址，标记 `coverSource=video.cover`。
2. 缺失时回退 `video.origin_cover.url_list`，标记 `coverFallback=true` 和 `coverVerification=fallback_not_display_verified`。
3. 两者均无则留空。`dynamic_cover` / `animated_cover` 不静默写入静态「封面」字段。

`origin_cover` 与展示封面可能是两张不同图片，不能因为名字含 origin 就优先选它。需要严格与页面一致或出现用户反馈时，核对该作品卡片的 `img.currentSrc` 与候选 URL 的资源路径；域名副本、缩放裁剪参数、签名变化需与资源 ID 差异区分。

图文独立处理：`images[0].url_list` 只作为候选，标记 `coverVerification=needs_homepage_check`。写入面向展示的封面前，应核验该作品主页卡片；未核验时保留候选或明确注明，而不是宣称展示一致。

每条保存 `cover`、`coverSource`、`coverFallback`、`coverVerification` 与采集时间。API 选择并不等于逐条 DOM 核验，`api_display_cover` 明确表达这一点。

源 CDN 地址可能有 `x-expires` / `x-signature`，不可宣称永久有效。报告可保存业务所需图片地址，但不把真实签名链接、Cookie、Token、登录态或采集结果提交到 Skill / Git。长期保存为飞书附件或 OSS 文件属于额外外部写入，取得授权后执行。

## 完成状态与回写

- `postApiComplete` 只在接口明确 `has_more=0`、且本轮无解析错误时为 true。
- `targetCoverageComplete=true` 仅代表给定目标 ID 已收齐，不代表账号全量。
- 无新增、滚动上限、页面关闭、请求错误都必须保留 `stopReason`。首批记录数不等于主页作品总量。
- 发现验证码、访问异常或账号风险就停止；浏览器/页面关闭也停止，不把后续未尝试作品判成源失效。
- 回写前读取目标表 schema、已有记录和状态枚举；只更新授权字段，保留人工标注与其他任务的新数据。
- 不用当前抓取值补造 D1～D30 历史指标，不把后续刷新时间当作首次发现时间。
- 已有封面修复需要明确修复范围；更新 Skill 不自动修改历史记录。

## 验证

```bash
python3 -B scripts/test_profile_data.py
```

测试覆盖展示封面优先级、显式回退、动态图不冒充静态封面、图文待核验、作者绑定、目标过滤与去重、0/null 区分和接口错误。仅用合成数据，不保存真实用户资料。
