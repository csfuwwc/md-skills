# News 多图轮播规范

仅在用户明确要求一篇 News 展示两张或更多图片时读取并执行本规范。普通单图文章继续使用 `article.image`，不要为了统一格式批量迁移旧文章。

## 数据模型与边界

- `article.image`：使用用户确认的第 1 张图，供博客列表、分享卡片和没有 gallery 时的页面回退使用。
- `custom.news_gallery`：ARTICLE 所有者的 `list.file_reference` metafield，值为按展示顺序排列的 `MediaImage` GID 数组。第 1 个引用必须与题图表达同一张图片。
- 图片已在 Shopify Files 中且能取得 `MediaImage` GID 时直接复用；否则上传后等待文件状态为 `READY`，再写文章。
- 每张真实图片都写准确、可读的 alt。gallery 在各语言版本间共用，不重复上传；标题、正文和摘要仍按主流程注册翻译。
- 只更新目标文章的 gallery。不得清空、迁移或改写其他文章的 gallery；来源 metafield 也必须保持独立。
- 写入前只读检查 metafield definition。若 `custom.news_gallery` 不存在，先说明将创建的 ARTICLE / `list.file_reference` 定义并取得外部写入确认；不要创建同名异类型定义。

`metafieldsSet` 的值是 JSON 字符串，顺序就是前台顺序：

```graphql
mutation SetNewsGallery($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields { id namespace key type value }
    userErrors { field message code }
  }
}
```

```json
{
  "metafields": [{
    "ownerId": "gid://shopify/Article/ARTICLE_ID",
    "namespace": "custom",
    "key": "news_gallery",
    "type": "list.file_reference",
    "value": "[\"gid://shopify/MediaImage/FIRST\",\"gid://shopify/MediaImage/SECOND\"]"
  }]
}
```

## 主题渲染契约

当前 News 详情轮播位于正式主题的 `sections/funcinating-main-article.liquid`。每次操作前仍要回读当前 live theme，不把本地仓库或历史主题当成线上证据。

- gallery 为空：回退显示 `article.image`。
- gallery 只有 1 张：显示静态首图，不显示箭头或圆点。
- gallery 有 N 张：真实顺序保持不变，物理轨道为“末图克隆 + N 张真实图 + 首图克隆”，初始停在物理索引 1。
- 从最后一张点击向右：继续向右滚到首图克隆，滚动结束后用 `behavior: auto` 静默跳回真实首图。从第一张点击向左时做对称处理。不能出现先向反方向滚回首图的视觉倒退。
- active index 和圆点只计算真实图片，克隆图加 `aria-hidden="true"` 且 alt 为空。
- 桌面箭头默认透明且不可点击，仅在图片区域 `:hover` 或 `:focus-within` 时出现；移动端不显示箭头，保留原生横向滑动。
- 左右箭头必须是带本地化 `aria-label` 的 button。真实 slide 提供序号语义，圆点可点击并同步 `aria-current`。
- 尊重 `prefers-reduced-motion`；降级为即时移动。尺寸变化后保持当前真实图片，不跳回错误位置。
- 图片区域保持稳定比例，使用 `object-fit: contain` 避免裁切；首张 eager/high priority，其余 lazy。

## 实施与发布顺序

1. 向用户列出图片并确认顺序，第 1 张同时作为题图。
2. 解析或上传图片，等待全部 `MediaImage` 可用并设置 alt。
3. 创建或更新文章的 `article.image`，再给该文章写 `custom.news_gallery` 的有序引用。
4. 主语言内容变化后重取 digest，再为所有已发布目标 locale 注册 `title`、`body_html`、`summary_html`；gallery 引用本身不按 locale 复制。
5. 先做本地或 unpublished theme 预览。只有用户明确确认“上线/发布”后，才更新 live theme 或把文章设为 published。
6. 分开处理正文事件时间和文章可见时间。`publishDate` 使用用户确认的 GMT+8 文章可见时间，写入前转换为 UTC；只给日期未给时间时必须询问，不能用操作当天或默认钟点补齐。

如果当前 live theme 缺少上述能力：

- 先拉取 live theme 的目标 section 到临时目录，只在这份线上基线加入 gallery 代码。
- 不直接推送工作区同名文件，因为它可能夹带其他未上线改动。
- 按 `shopify-liquid` Skill 搜索官方文档并验证 Liquid；运行聚焦测试，检查 diff 只包含 gallery 结构、脚本和样式。
- 取得上线确认后只推送目标 section，`--nodelete --allow-live`；随后重新拉取并比较 SHA。

## 验收清单

### Admin API 回读

- 目标 article GID、handle 和发布状态正确。
- `custom.news_gallery.type == "list.file_reference"`，引用数为 N，GID 和 URL 顺序与用户确认一致。
- `article.image` 与 gallery 第 1 张一致，来源 metafield 未被覆盖。
- 每个目标 locale 都有 `title`、`body_html`、`summary_html`；旧文章 gallery 保持原值。

### 页面与交互

- 用 `?preview_theme_id=<LIVE_THEME_ID>` 绕开 Shopify 整页缓存；正式发布后公共 URL 返回 HTTP 200。
- HTML 中真实 slide 数为 N；N > 1 时另有 2 个克隆 slide，所有目标图片文件名都已渲染。
- 桌面初始箭头不可见，鼠标移入图片或键盘 focus 进入后可见。
- 最后一张向右继续前进到第一张；第一张向左继续后退到最后一张，两次均无反向回滚闪动。
- 圆点状态与真实图片一致；移动端手势可滑动；缩放和 reduced-motion 模式下索引稳定。
- 单图和无 gallery 的旧 News 仍走原回退，不受轮播逻辑影响。

通过上述回读和页面验收后，才能向用户表述“多图轮播已上线”。
