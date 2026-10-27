# News 多图轮播规范

用户要求一篇 News 展示两张或更多图片，或维护已有轮播、修复其 alt 时，完整读取并执行本规范。普通单图文章继续使用 `article.image`，不要为了统一格式批量迁移旧文章。

## 数据模型与边界

- `article.image`：使用用户确认的第 1 张图，供博客列表、分享卡片和没有 gallery 时的页面回退使用。
- `custom.news_gallery`：ARTICLE 所有者的 `list.file_reference` metafield，值为按展示顺序排列的 `MediaImage` GID 数组。第 1 个引用必须与题图表达同一张图片。
- `custom.news_gallery_alt_i18n`：ARTICLE 所有者的 `json` metafield，按 MediaImage 数字 ID 字符串 → Shopify locale → alt 保存已核验的原生翻译，供国际站轮播读取。不是按序号、文件名或标题建立映射。
- 图片已在 Shopify Files 中且能取得 `MediaImage` GID 时直接复用；否则上传后等待文件状态为 `READY`，再写文章。
- 每张真实图片都写准确、可读的 alt。gallery 在各语言版本间共用，不重复上传；标题、正文和摘要仍按主流程注册翻译。
- 只更新目标文章的 gallery。不得清空、迁移或改写其他文章的 gallery；来源 metafield 也必须保持独立。
- 写入前只读检查 metafield definition。若 `custom.news_gallery` 不存在，先说明将创建的 ARTICLE / `list.file_reference` 定义并取得外部写入确认；不要创建同名异类型定义。
- alt 映射写入前检查已有实例的 type/value/compareDigest 及已有 definition（若有）。类型不符先报告，不覆盖；无需为每篇文章另建全局 definition。本次授权只覆盖目标文章，不批量补写历史文章。

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
- 国际站真实图片的 alt 优先取当前图片 ID 与 `localization.language.iso_code` 对应的映射；空值回退到原生 media alt，再回退到已本地化文章标题。回退仅用于渲染容错，不能据此判定目标语言验收通过。克隆图不参与此取值，始终 `alt=""`。中国站分支保持不变。

## 多语言 alt：原生翻译与渲染映射同时维护

### 已证实的坑位（2026-10-27）

本店实测：两张 MediaImage 的原生翻译已存在且 `outdated:false`，但经 `custom.news_gallery` 的 file_reference 读取时，`gallery_image.alt`、`preview_image.alt` 及不传显式 alt 的 `image_tag` 仍返回英文；同页 `article.image` 的 ArticleImage 能返回本地化 alt。因此“已注册翻译”不代表“前台已生效”，只删除 `image_tag` 的显式 alt 也未解决。此为本店当时链路的实测，不推定所有 Shopify 媒体永远如此。以后如想移除兼容映射，必须先逐语言证明公共页面原生渲染已正确，并另获主题变更授权。

### 数据格式与同步顺序

示例仅展示两种语言；实际必须覆盖现查的全部目标语言，不能把示例当成固定语言清单：

```json
{
  "123456789": {
    "en": "FUNCINATING booth entrance at the exhibition.",
    "zh-CN": "展会现场的范趣町展位入口。"
  },
  "987654321": {
    "en": "Plush collectibles on the display shelves.",
    "zh-CN": "展架上陈列的毛绒收藏品。"
  }
}
```

1. 现查 article、题图 ArticleImage、gallery 中每个 MediaImage 的实际 GID、顺序、目标 locale 与 storefront 路由。语言码用 Shopify 原值（如 `zh-CN`），不是 URL 路径（如 `zh-sg`）。不要写死历史上的五种语言或主题 ID。
2. 为每张真实图片准备准确、独立的描述；不照抄标题、不堆关键词。复用图片，不按语言重复上传。相同 CDN 图片的 ArticleImage 与 MediaImage 是不同资源，必须分别查询，不推断其 GID 相同。
3. 写主语言 alt 后重新获取每个图片资源的 `translatableContent` key/digest；按实际 schema 给 ArticleImage 和所有 MediaImage 注册各目标语言的原生 alt 翻译。不要使用文章正文的 digest，也不要猜图片翻译 key。复用的 MediaImage 翻译会影响其他引用者，若拟改已有文案需核对影响，超出授权时先询问。
4. 独立回读原生 alt 和所有翻译，值须与预期一致且 `outdated:false`；出现 userErrors 或漏项即停。将这些已核验值复制到 `custom.news_gallery_alt_i18n`，不另翻译一份可能分歧的文案。主语言也入映射。
5. `metafieldsSet` 使用当前 ARTICLE owner、namespace=`custom`、key=`news_gallery_alt_i18n`、type=`json`，value 为 JSON 字符串。首次创建用 `compareDigest:null`；已有值先读后合并，用当前 compareDigest 防并发覆盖。冲突时重读，不盲目重试覆盖；保留未授权删除的语言或图片条目。API 不支持该并发字段时先核实可用方案，不悄悄放弃并发保护。
6. 再独立回读映射，按当前 gallery ID × locale 比对预期、原生值、映射值。换图须用新 ID 补齐；仅重排不改 ID；改 alt 时原生翻译与映射必须同次维护。额外保留的旧 ID 不得代替当前图片覆盖检查。
7. 检查 live theme 已有下述读法；已具备则只写数据，不重复上传主题。单纯 alt 修复须比对正文、SEO、作者、可见时间、来源、图片及顺序均未意外改变。

国际站真实图片循环中的现行读法（`gallery_alt` 最终传给 `image_tag`，克隆分支仍传空字符串）：

```liquid
assign gallery_alt = gallery_image.alt | default: article_display_title
if is_china_storefront == false
  assign gallery_alt_key = gallery_image.id | append: ''
  assign gallery_alt_translations = article.metafields.custom.news_gallery_alt_i18n.value
  assign gallery_localized_alt = gallery_alt_translations[gallery_alt_key][localization.language.iso_code]
  if gallery_localized_alt != blank
    assign gallery_alt = gallery_localized_alt
  endif
endif
```

沿用当前主题的图片 source/URL 与转义机制，不修改样式或轮播 JS 来修 alt。原生 MediaImage / ArticleImage 翻译仍需保留，映射只是兼容读取层。

## 实施与发布顺序

1. 向用户列出图片并确认顺序，第 1 张同时作为题图。
2. 解析或上传图片，等待全部 `MediaImage` 可用并设置 alt；按上节维护所有图片资源的原生翻译。
3. 创建或更新文章的 `article.image`，再给该文章写 `custom.news_gallery` 的有序引用。
4. 主语言内容变化后重取 digest，再为所有已发布目标 locale 注册 `title`、`body_html`、`summary_html`；gallery 引用本身不按 locale 复制。图片翻译独立回读后同步 alt 映射。
5. 本地预览只供审稿，不能证明 Liquid alt 生效。发布前须在 Shopify 真实渲染的草稿预览或 unpublished theme 中逐语言验收；若草稿无法渲染，先报告验收限制，不为了测试擅自公开。只有用户明确确认“上线/发布”且发布前检查通过，才更新 live theme 或把文章设为 published；正式上线后再验公共 URL。
6. 分开处理正文事件时间和文章可见时间。`publishDate` 使用用户确认的 GMT+8 文章可见时间，写入前转换为 UTC；只给日期未给时间时必须询问，不能用操作当天或默认钟点补齐。

如果当前 live theme 缺少上述能力：

- 先拉取 live theme 的目标 section 到临时目录，只在这份线上基线加入 gallery 代码。
- 不直接推送工作区同名文件，因为它可能夹带其他未上线改动。
- 按 `shopify-liquid` Skill 搜索官方文档并验证 Liquid；运行聚焦测试，检查 diff 只包含 gallery 结构、脚本和样式。
- 取得上线确认后只推送目标 section，`--nodelete --allow-live`；随后重新拉取并比较 SHA。
- 若仅修 alt，diff 只能包含真实图片 alt 取值。先复现失败测试，再在 unpublished theme 验证；Liquid 校验需真实 snippet/locale 依赖。上传前重读 live 基线防并发覆盖；不得把诊断主题直接发布为正式主题。需刷新发布时也只操作原目标 live theme。

## 验收清单

### Admin API 回读

- 目标 article GID、handle 和发布状态正确。
- `custom.news_gallery.type == "list.file_reference"`，引用数为 N，GID 和 URL 顺序与用户确认一致。
- `article.image` 与 gallery 第 1 张一致，来源 metafield 未被覆盖。
- 每个目标 locale 都有 `title`、`body_html`、`summary_html`；旧文章 gallery 保持原值。
- 题图 ArticleImage 和各 MediaImage 的原生 alt 翻译均正确且未过期；映射 type 为 `json`，当前每个图片 ID × 每个目标 locale 均有非空正确值，与原生翻译一致。

### 页面与交互

- 可用 `?preview_theme_id=<LIVE_THEME_ID>` 辅助检查缓存；正式发布后必须在不带 preview 参数的公共 URL 上重做逐语言 alt 检查，HTTP 200 本身不算通过。
- HTML 中真实 slide 数为 N；N > 1 时另有 2 个克隆 slide，所有目标图片文件名都已渲染。
- 桌面初始箭头不可见，鼠标移入图片或键盘 focus 进入后可见。
- 最后一张向右继续前进到第一张；第一张向左继续后退到最后一张，两次均无反向回滚闪动。
- 圆点状态与真实图片一致；移动端手势可滑动；缩放和 reduced-motion 模式下索引稳定。
- 单图和无 gallery 的旧 News 仍走原回退，不受轮播逻辑影响。

### alt 验收矩阵与失败处理（硬闸）

- 对实际目标语言集合 L 和真实图片数 N，检查必须覆盖 L × N，不能只抽首图或中英文。浏览器 DOM 中读取每张真实 `img` 的实际 `alt`，包括未激活/懒加载 slide；确认 URL、页面实际语言及图片 ID/源文件对应关系，防止语言重定向和图片串位。
- 逐项记录：locale、页面 URL、图片 ID/顺序、预期 alt、原生值、映射值、DOM alt、pass/fail。按实际文本比较（允许 HTML 实体解码，不得把英文回退当合格翻译）；不要仅凭“非空”或是否含某语种字符判断。
- N > 1 时另验 2 个克隆图：`aria-hidden="true"` 且 `alt=""`；克隆不计入 N。列表题图逐语言单独检查 ArticleImage 路径，不能用详情轮播通过替代列表通过。
- 验收脚本须在覆盖不足、目标语言缺失、翻译过期、图片错位、alt 不匹配或克隆异常时非零退出；禁止 `altWarnings` 非空仍返回总体验收成功。未执行项记“未验证”，不能记 pass。
- 新增或修改共享主题读取逻辑时，至少回归一篇旧单图和一篇旧多图 News 的原有表现，并执行上述交互检查。旧文回退兼容通过不等于其全部语言历史缺陷已被修复，不得借此扩大改稿范围。
- 上线前失败：不发布，列明差异并在已授权范围内修正。上线后失败：报告“已公开但验收失败”，不宣称完成，不擅自改发布时间或下线；修复超出当前授权时先确认。无法验证真实页面时也必须明确阻塞。

通过原生翻译回读、映射回读、全语言逐图 DOM 验证及交互验收后，才能向用户表述“多图轮播已上线且验收通过”。交付时附实际语言数 × 图片数与证据位置，不以“应该生效”代替结果。
