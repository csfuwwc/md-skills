---
name: funcinating-news
version: 1.0.0
description: |
  基于某条新闻或话题，为 Funcinating(范趣町)Shopify news 博客生成一篇「事实扎实、
  中英双语、去 AI 味、可直接发布」的资讯。适用于：定期外部搜索到品牌相关动态、或自己拟一个
  话题时。内置六步流程(取现状→查证→骨架起草→去AI味→写入Shopify→验收)、固定信源清单、
  五拍内容骨架、合规红线(绝不编造)、以及 Shopify 文章读写的确切 GraphQL 与坑位。
  与 humanizer / humanizer-zh 组合使用。
license: MIT
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
一条线索即可:一个话题、一个 URL、一段事实、或一个已有文章 handle。

---

## 硬规则(先看，违反直接作废)
1. **绝不编造**。只写多源交叉验证过的事实。分不清真假的、只有单一未知来源的、"看起来合理"的细节——一律不写。反面教材:曾把「亮相曼谷/Union Mall 广告牌/东南亚热烈反响」当事实写进去，实际官宣里根本没有。宁可短，不可假。
2. **必去 AI 味**。EN 过 [humanizer]、ZH 过 [humanizer-zh]。硬约束:**成品无 em-dash（`—` / `——`）**；无 AI 词(打造/赋能/见证/彰显/persistent/underscore…)；不硬凑三段式；句子长短交错。
3. **中英都要**。EN 是原文(articleUpdate)，ZH 走 Shopify 原生翻译(translationsRegister 到 `zh-CN`)。两边都去 AI 味。
4. **标注来源**。给用户审稿时附来源链接；文章 `custom.source_url` 填真实外链(优先官方 ins/X/TikTok；别填自家页面占位)。

---

## 六步流程
前三步是人的判断(查证+起草+审稿，不能省)，后三步是机械操作(可脚本化)。

### ① 取现状
若是改已有文章，先拉它的现有内容 + 已有翻译 + 发布状态 + 来源，搞清缺什么、哪句可疑:
```
shopify store execute -s qs0nxk-ft.myshopify.com -j -q '{
  article(id:"<ARTICLE_GID>"){ isPublished
    su:metafield(namespace:"custom",key:"source_url"){value}
    sn:metafield(namespace:"custom",key:"source_name"){value} }
  translatableResource(resourceId:"<ARTICLE_GID>"){
    translatableContent{key value digest}
    translations(locale:"zh-CN"){key value} } }'
```
拿 article GID：`{ blogs(first:5){nodes{handle articles(first:25){nodes{handle id}}}} }`，news 博客 handle=`news`。

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

### ④ 给用户审
EN + ZH 草稿 + 来源链接，让用户核事实。**通过再写。**

### ⑤ 写入 Shopify(注意坑)
EN 用 `articleUpdate`（新建用 `articleCreate`，需 `blogId`）:
```
mutation($id:ID!,$article:ArticleUpdateInput!){
  articleUpdate(id:$id,article:$article){ article{title} userErrors{field message} } }
# article 可含: title, body(HTML), summary(HTML), isPublished, publishDate, image:{altText,url}
```
- ⚠️ 发布日期字段是 **`publishDate`（DateTime），不是 `publishedAt`**。放出隐藏文章=`isPublished:true`；补真实日期=`publishDate:"2025-11-06T08:00:00Z"`(按事件真实时间，别让它挂成今天)。
- ⚠️ **图片 alt 常残留旧标题**：`image:{altText:"<新描述>", url:"<现有CDN url>"}`(url 传当前值以保持图片不变)。
- ⚠️ **EN 改动后 digest 会变**：注册 ZH 前必须**重取** `translatableContent.digest`。
- 来源外链：`metafieldsSet(metafields:[{ownerId:"<ARTICLE_GID>",namespace:"custom",key:"source_url",type:"url",value:"<真实外链>"}])`。

ZH 走 `translationsRegister`:
```
mutation($rid:ID!,$translations:[TranslationInput!]!){
  translationsRegister(resourceId:$rid,translations:$translations){ translations{key} userErrors{field message} } }
# 每项: {locale:"zh-CN", key:"body_html"|"summary_html"|"title", value:<中文HTML>, translatableContentDigest:<重取的digest>}
```

### ⑥ 验收
- ⚠️ **Shopify 整页缓存很黏、且忽略 `?cb=` 参数**：验证要用 `?preview_theme_id=<LIVE_THEME_ID>` 绕过缓存渲染。
- grep 确认删掉的假信息 **0 残留**(标题/正文/摘要/图 alt/meta 都查)。
- 字数 200-500、**无 em-dash**、EN 和 zh-sg 两个 locale 都对、内链有效。

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
