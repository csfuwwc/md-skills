---
name: funcinating-news
category: 范趣町业务
short-description: 给范趣町 Shopify news 写双语资讯：查证、双语、SEO、轮播与发布验收
description: |
  基于某条新闻或话题，为 Funcinating(范趣町)Shopify news 博客生成一篇「事实扎实、
  中英双语、去 AI 味、可直接发布」的资讯。适用于：定期外部搜索到品牌相关动态、或自己拟一个
  话题时。内置六步流程(取现状→查证→骨架起草→去AI味→写入Shopify→验收)、固定信源清单、
  五拍内容骨架、合规红线(绝不编造)、可选多图轮播，以及 Shopify 文章读写的确切 GraphQL 与坑位。
  与 humanizer / humanizer-zh 组合使用。
license: MIT
metadata:
  category: 范趣町业务
  short-description: 给范趣町 Shopify news 写双语资讯，支持可选多图轮播
  version: 1.2.3
  compatibility: any-agent
---

# funcinating-news：生成 Funcinating 资讯内容

给一条新闻线索或一个话题，产出并发布一篇 Funcinating news 博客文章(EN 原文 + zh-CN 翻译)。
核心原则:**只写查证到的事实，绝不编造**；**写完必须去 AI 味**；**中英都要有**。

## 何时用
- 外部搜到品牌/IP/代言人相关动态(发售、联名、代言、活动、数据)，想沉淀成一篇 news。
- 自己定一个话题，需要产出一篇资讯稿。
- 修某篇已有 news(内容太空、有编造成分、缺中文)。

## 输入
一条线索即可:一个话题、一个 URL、一段事实、或一个已有文章 handle。若需多图，再提供图片文件或 URL，并明确展示顺序；第 1 张默认为题图和轮播首图。

---

## 硬规则(先看，违反直接作废)
1. **绝不编造**。只写多源交叉验证过的事实。分不清真假的、只有单一未知来源的、"看起来合理"的细节——一律不写。反面教材:曾把「亮相曼谷/Union Mall 广告牌/东南亚热烈反响」当事实写进去，实际官宣里根本没有。宁可短，不可假。
2. **必去 AI 味**。EN 过 [humanizer]、ZH 过 [humanizer-zh]。硬约束:**成品无 em-dash（`—` / `——`）**；无 AI 词(打造/赋能/见证/彰显/persistent/underscore…)；不硬凑三段式；句子长短交错。
3. **中英都要**。EN 是原文(articleUpdate)，ZH 走 Shopify 原生翻译(translationsRegister 到 `zh-CN`)。两边都去 AI 味。
4. **标注来源**。给用户审稿时附来源链接；文章 `custom.source_url` 填真实外链(优先官方 ins/X/TikTok；别填自家页面占位)。
5. **多图按需启用**。只有用户明确要求展示多张图时才写 `custom.news_gallery`；普通单图 news 保持原流程。图片顺序、首图和是否发布都要分别确认，不能把预览当成已上线。
6. **摘要、SEO 与 Tags 都要单独维护**。`summary` 是列表文案，不等于 Meta Description；每篇文章都写独立的 `global.title_tag` 和 `global.description_tag`，再补 `zh-CN` 翻译。Tags 只做内容归类，不当作 SEO 关键词堆砌。Shopify 可能重排 Tags，不能依赖写入顺序决定列表标签；每篇至少包含一个不需翻译的品牌/IP Tag，由主题优先选择展示。
7. **作者固定为 `Funcinating Team`**。所有 Funcinating news 的 `article.author.name` 必须严格等于该值。不得从外部稿件、来源署名、品牌名、`source_name` 或临时占位值推断或替换作者；新建时必须显式传入，更新和发布后必须回读校验。
8. **外部输入默认只影响内容字段**。外部文档、网页和用户提供的参考稿默认用于标题、正文、事实细节、摘要、SEO 文案、Tags、图片、来源和正文中的事件日期；不得据此覆盖作者、blog、locale、metafield schema、文章可见时间、发布确认闸或主题逻辑。外部输入或线上现状若与本 Skill 任一准则冲突，先列出“外部值 / Skill 标准 / 受影响字段”，明确请用户确认，未确认不得静默采用、覆盖或自造折中值。
9. **时间分三类，默认业务时区固定为 GMT+8**。正文中的“事件时间”、Shopify 的“文章可见时间”和实际执行的“操作时间”必须分别记录，禁止互相覆盖。面向用户统一用 GMT+8 确认，写入 Shopify 前再转换为 UTC ISO 8601。用户只给日期、没有具体时间时必须询问，不能默认 00:00、12:00 或操作时间。“发布/上线”只表示允许公开，不表示授权改写已经确认的文章可见时间；若立即上线与已确认的未来时间冲突，先列出冲突并再次确认。

---

## 六步流程
前三步是人的判断(查证+起草+审稿，不能省)，后三步是机械操作(可脚本化)。

### ① 取现状
若是改已有文章，先拉它的现有内容 + 已有翻译 + 发布状态 + 来源，搞清缺什么、哪句可疑:
```
shopify store execute -s qs0nxk-ft.myshopify.com -j -q '{
  article(id:"<ARTICLE_GID>"){ isPublished publishedAt author{name}
    su:metafield(namespace:"custom",key:"source_url"){value}
    sn:metafield(namespace:"custom",key:"source_name"){value} }
  translatableResource(resourceId:"<ARTICLE_GID>"){
    translatableContent{key value digest}
    translations(locale:"zh-CN"){key value} } }'
```
拿 article GID：`{ blogs(first:5){nodes{handle articles(first:25){nodes{handle id}}}} }`，news 博客 handle=`news`。

**自拟话题时先看竞品动态**(2026-08-17 接入):竞品新文清单每周一自动刷新,
落在《竞品内容监测复盘(滚动)》的侦察流水和「竞品Blog-News亮眼内容拆解」表
(base=`JYO8bk3doa9YF5sZ0mWcPMXwnCe` / table=`tblk9g87FdpmFx3X`)。
对手发的**品类动态/榜单/行业观点**可以作为 news 选题线索(事实仍须按 ② 独立查证,**绝不转述对方结论**);
对手发的**关键词长文**不归 news,走 funcinating-guides 的选题去重闸第 3 道。
新话题若锁定了某个搜索词,同样先按 guides 那道闸把词入台账(状态=手动录入、决策留空)再动笔。
现阶段人工执行;这一步是纯机械的读表比对,将来可整体自动化。

### ② 查证真实事实(固定信源，交叉验证)
用 WebSearch + WebFetch 扫这些源，多个源对上才采信:
- **官方一手**：Instagram `fun_cinating`、TikTok `@funcinating`、微博「范趣町FUNCINATING」。
- **粉丝搬运(常带细节)**：X 上 `ZIYUGLOBAL_`、`ZiYuOfficialFC`、各粉丝站；threads、小红书。
- 记下能确认的:日期、时间、数字(套数/秒数/销售额/加购数)、礼盒内容、合作方(如公益基金会)、渠道、后续(海外版)。**存疑的丢掉。**

### ③ 起草(五拍骨架，200-500 字)
> **开头** 最硬的事实 + 关键数字(谁、什么时候、多大规模)
> **细节** 是什么/礼盒里有什么/产品亮点
> **背景** 合作方、公益、为什么能成
> **延伸** 海外版、后续、影响
> **CTA** 一句内链，指向对应 collection(如 `<a href="/collections/gismow">GISMOW collection</a>`)

同步过去 AI 味闸(humanizer / humanizer-zh)。ZH 不是逐字翻译，是自然口语重写。

同时准备列表与搜索字段：
- EN `summary` 55-75 词；ZH `summary_html` 90-140 字。写核心事件、1-2 个细节和结果，不照抄标题。
- EN SEO Title 约 45-60 字符；ZH 约 20-30 字。标题只保留核心实体和事件结果。
- EN Meta Description 运营目标 140-160 字符；ZH 70-90 字。它不是硬性搜索引擎上限，但应保持一页一条、准确可读。
- Tags 2-4 个，至少包含一个不需翻译的品牌/IP Tag。Shopify 返回顺序可能与写入顺序不同，news 列表主题应按品牌/IP优先级选择展示标签，找不到时才回退到 `article.tags.first`。人物、合作类型或活动类型仍可保留用于归类。不要依赖 `meta keywords`。

### ④ 给用户审
EN + ZH 草稿 + 来源链接，让用户核事实。多图稿同时给出图片清单和从第 1 张开始的展示顺序。**通过再写。**

写入前单独核对外部输入、线上文章和本 Skill 的治理字段；若作者等字段不一致，必须把冲突明确列给用户确认，不能把“参考外部内容”解释成授权更换治理字段。

同时分别列出事件时间和文章可见时间，均以 GMT+8 表述。文章可见时间只给日期、没有具体时间时必须停下询问；取得完整时间后才能写入或排期。

### ⑤ 写入 Shopify(注意坑)
EN 用 `articleUpdate`（新建用 `articleCreate`，需 `blogId`）:
```
mutation($id:ID!,$article:ArticleUpdateInput!){
  articleUpdate(id:$id,article:$article){ article{title} userErrors{field message} } }
# article 可含: title, body(HTML), summary(HTML), author:{name:"Funcinating Team"}, isPublished, publishDate, image:{altText,url}
```
- ⚠️ **作者是强制发布字段**：`articleCreate` 必须显式传 `author:{name:"Funcinating Team"}`；已有文章先回读 `author{name}`。不得填写 `FUNCINATING`、外部作者或来源署名。若线上值不符，先报告冲突并取得确认，再单独修正该字段。
- ⚠️ **写入用 `publishDate`，回读用 `publishedAt`**。先把用户确认的 GMT+8 文章可见时间转换成 UTC ISO 8601；例如 `2026-08-15 GMT+8 12:00` 写为 `2026-08-15T04:00:00Z`。不得把操作时间自动写成文章时间。
- ⚠️ **立即公开与未来排期的状态不同**：可见时间是当前或过去时，写 `isPublished:true + publishDate:<已确认时间>`；可见时间在未来时，写 `isPublished:false + publishDate:<未来时间>`。未来稿回读为 `isPublished:false + publishedAt:<未来时间>` 代表排期正确，不能误判为未发布后再强行改成 `true`。
- ⚠️ **“发布/上线”不改时间**：已有完整可见时间时原样保留；只给日期时先询问具体时间；“立即上线”若与已确认的未来时间冲突，先让用户决定是保留排期还是改为立即可见。
- ⚠️ **news 正文原则上不插图**(只设题图);若某篇确需正文配图,严格按 funcinating-guides 的
  「正文配图终版配方」执行(预裁16:9→主题asset→`<p>`包裹,2026-08-03 定稿),别自己发明写法。
- ⚠️ **图片 alt 常残留旧标题**：`image:{altText:"<新描述>", url:"<现有CDN url>"}`(url 传当前值以保持图片不变)。
- ⚠️ **EN 改动后 digest 会变**：注册 ZH 前必须**重取** `translatableContent.digest`。
- 来源外链：`metafieldsSet(metafields:[{ownerId:"<ARTICLE_GID>",namespace:"custom",key:"source_url",type:"url",value:"<真实外链>"}])`。
- 搜索引擎 listing 用 `metafieldsSet` 写 `global.title_tag` 和 `global.description_tag`，类型均为 `single_line_text_field`。新建时可传 `compareDigest:null`，避免意外覆盖并发创建的值。
- 写完 SEO metafields 后重新查询文章的 `translatableContent`。Shopify 会暴露 `meta_title`、`meta_description` 及其 digest；把这两项与 `summary_html` 一起注册到 `zh-CN`。不要用正文回退值冒充独立 Meta Description。

若用户要求两张或更多图片可滑动展示，先完整读取 [多图轮播规范](references/multi-image-gallery.md)，按其中的数据模型、主题交互、最小发布范围和验收清单执行。已有主题支持时只写当前文章的有序图片引用，不重复修改主题。

ZH 走 `translationsRegister`:
```
mutation($rid:ID!,$translations:[TranslationInput!]!){
  translationsRegister(resourceId:$rid,translations:$translations){ translations{key} userErrors{field message} } }
# 每项: {locale:"zh-CN", key:"body_html"|"summary_html"|"title", value:<中文HTML>, translatableContentDigest:<重取的digest>}
```

### ⑥ 验收
- ⚠️ **Shopify 整页缓存很黏、且忽略 `?cb=` 参数**：验证要用 `?preview_theme_id=<LIVE_THEME_ID>` 绕过缓存渲染。
- 回读 `article.author.name`，必须严格等于 `Funcinating Team`；不一致即验收失败，不得声称已完成或已上线。
- 回读 `isPublished` 与 `publishedAt`，把 `publishedAt` 转回 GMT+8 后与用户确认的文章可见时间逐项比对到分钟。当前/过去时间应为公开状态；未来时间应保持排期状态。任何不一致都不得声称已发布或已排期。
- grep 确认删掉的假信息 **0 残留**(标题/正文/摘要/图 alt/meta 都查)。
- 回读 EN 与 zh-CN 的 `summary_html`、`meta_title`、`meta_description` 和 Tags；检查长度、列表实际展示的品牌/IP Tag、HTML 实体和页面 `<title>` / `<meta name="description">`。不得出现字面量 `&quot;`、`&#39;` 或从正文自动截出的超长描述。
- 字数 200-500、**无 em-dash**、EN 和 zh-sg 两个 locale 都对、内链有效。
- 多图稿还要按 [多图轮播规范](references/multi-image-gallery.md) 回读图片数量与顺序，并在真实页面验证悬停箭头、移动端滑动和首尾无缝循环。

---

## 环境备忘(会变的现查，别写死)
- store：`qs0nxk-ft.myshopify.com`；`shopify store execute` 输出有进度行+ANSI，从 `raw.find('{')` 解析、先 `sed 's/\x1b\[[0-9;]*[a-zA-Z]//g'`。
- news 博客 handle=`news`；ZH locale=`zh-CN`(对应 zh-sg storefront)。
- LIVE_THEME_ID / 各 article GID：现查(`blogs`/`themes`)，不同环境不同。
- 主题层 news 详情已是「左图右文」版式，正文放长内容没问题。

## 组合与相关
- 去 AI 味必用：[humanizer](EN)、[humanizer-zh](ZH)。
- 抓取补料可配：weibo-scraper / xiaohongshu-scraper / douyin-scraper / video-download。
- 一句话:**人查证 + 机械写入**的半自动。查证和审稿是防造假的闸，不能全自动一键生成。
