---
name: shopify
version: 1.0.0
description: |
  Shopify 独立站(Funcinating/范趣町)新增商品的标准上架流水线。同事只管「提供素材」,
  skill 把 SEO/handle/metafield/FAQ/集合/结构化数据/多语言/写回上架 全包,只在缺输入、
  需拍板、要确认上线时找人。5 步:sync-pull → audit → optimize → translate → confirm-publish。
  无「审核」环节——「确认上线」是唯一人工闸。飞书表=工作台+SSOT,Shopify↔飞书同步。
  与 humanizer / humanizer-zh 组合。★用前必跑 `scripts/preflight.py` 自检(config/授权/依赖应用),缺就按提示补★。业务标识读 config;token 走 keychain/.env.local 不写死。
license: MIT
compatibility: any-agent
---

# shopify:独立站商品上架流水线

> ⚠️ **第一步永远是自检**:`cd scripts && python3 preflight.py`。它会查 config.local.json 建了没、飞书/Shopify 授权就绪没、依赖的 Shopify 应用装了没——**没绿之前别跑后面的脚本**(脚本本身也有守卫,缺 config 会直接拦住并指回这里)。换设备/换人第一件事就是它。


**核心模型**:**同事 = 提供者 + 最终确认**;**skill = 专家,把专业活全干**。skill 只在 3 种时候找人:①缺必要输入→提醒补 ②遇决策→让拍板 ③全弄好→**确认上线(唯一的闸,没有独立"审核")**。

## 何时用
- 同事在 Shopify 建了草稿商品,要走完整上架(内容/SEO/GEO/多语言/集合/结构化/索引)。
- 批量补齐/优化已有商品。
- 想让「换 agent、换人」都能一致跑完上架。

## 前提(跑之前)
1. **config(必做)**:`cp config.example.json config.local.json`,在 `config.local.json` 填你的 Feishu 表 `app_token`/`table_id`(从表 URL 取;★这项不进公开仓库、只在本地;换设备各自建一份★)。运行时合并 example + local。
2. **授权**:Shopify 走 `shopify store execute`(自带鉴权);Feishu 走 `lark-cli --profile <config.feishu.profile> --as user`(keychain 托管)。**任何 token 都别写进文件。**
3. **依赖**:`shopify` CLI、`lark-cli`、`python3`;多语言深挖见飞书《多语言适配指南(复用手册)》。

## 实体(entity)—— 一套脚本,三个资源
本 skill 用 `--entity product|collection|article` 覆盖 3 类 Shopify 资源,各自一张飞书表(config.entities),字段映射在 `scripts/entities.py`。**新增实体只在 entities.py 加一段 + config 加表**。
- `product`(商品)· `collection`(集合,editorial/faq/IP卡)· `article`(文章,news/guides)· `page`(页面,about/faq/政策/信任页)—— 均 pull→audit→writeback E2E 闭环
- 所有脚本都接 `--entity`:`sync_pull.py --entity collection` / `audit.py --entity article` / `sync_writeback.py --entity collection`。默认 product。

## 步骤 0 · `preflight`(初始化自检)· ✅ 已脚本化 —— **每次上手先跑**
- **跑法**:`cd scripts && python3 preflight.py`
- **查什么**:①`config.local.json` 是否建好并填了 feishu 表标识 ②飞书授权(能否读表)③Shopify 授权(能否连店)④主题访问(`.env.local` 含 THEME_TOKEN,仅步骤4/改主题需要)⑤**列出流水线依赖的 Shopify 应用清单让你确认已装**(如 Translate & Adapt;后台 API 查不到、须人工确认,配 `config.required_apps`)。
- **缺就提示怎么补**(建 config / 跑 lark-cli auth / 配 shopify 凭证),全 ✅ 才开始 sync_pull。新设备/换人第一件事就跑它。

## 字段契约(飞书表 59→现 54 字段,4 桶)
- **① 镜像**(Shopify→表,只读回填):Product ID(幂等键)· handle · 商品URL · 状态 · Vendor · 变体/SKU/价/库存 · 主图 · category
- **② 内容(双向)**(表内优化→确认后写回):商品名称 · 描述EN/中 · SEO Title/描述 EN/中 · Tags · `custom.*`(material/height/box_size/hidden_odds/series/scenario_copy/faq)· 目标IP/品类/场景集合
- **③ 规划(表内,不同步)**:IP角色 · 商品类型 · 主/辅关键词 · 搜索意图 · 页面角色 · FAQ主题 · Schema优先级 · 资料来源 · 运营优先级 · 备注
- **④ 流程状态(表内)**:内容审核状态(状态流)· 写回状态/时间/错误 · 索引/Schema/FAQ校验状态 · 负责人 · 上线验收 · 同步日期

**状态流**:`待补素材` →(同事补硬缺)→ `待拍板` →(同事定 handle/集合/术语)→ `待确认上线` →(同事确认)→ `已上线`
**视图**:01 待补/待拍板 · 03 待确认上线 · 04 SEO-GEO 验收(索引/schema 空)

---

## 步骤 1 · `sync-pull`(拉草稿进表)· ✅ 已脚本化
- **跑法**:`cd scripts && python3 sync_pull.py [--all | --status draft] [--dry-run] [--limit N]`(默认只拉 draft;`--dry-run` 只看计划不写)。已验证:按 Product ID 幂等 upsert、镜像总刷、内容仅填空、URL 字段 `{link,text}`、多选/数字/日期类型感知、集合归属自动归类(config.collections)。
- **触发**:同事建好草稿后 / 定期。**纯读 Shopify,不回写。**
- **逻辑**:
  1. GraphQL 拉商品(默认 `query:"status:draft"`,可指定/全量):`id handle title descriptionHtml vendor productType tags status category{fullName} seo{title description} options{name values} variants(first:100){edges{node{sku title price inventoryQuantity}}} media featuredImage{url altText} collections(first:20){edges{node{handle title}}} metafields(first:50){edges{node{namespace key type value}}}`。用 `--output-file` 落 JSON(ANSI 会污染多字节)。
  2. 按 **Shopify Product ID** upsert 进飞书表(`lark-cli base +record-upsert` 或 `api ...records/batch_update`),有则更新①镜像、无则新建行。
  3. ②内容字段**仅填空、不覆盖**(不动运营已优化的)。
  4. **集合归属**写入 目标IP/品类/场景集合(★老坑:手动拉常漏集合,务必拉★)。
  5. 盖 `最近Shopify同步日期`;新草稿 `内容审核状态=待补素材`。
- **铁律**:幂等键=Product ID(绝不重复行)· 内容字段绝不覆盖非空 · handle 只镜像不回写 · 逐商品失败记录不中断。
- **验收**:每草稿一行,镜像齐、集合有、状态=待补素材,抽验与 Shopify 一致。

## 步骤 2 · `product-audit`(核查缺啥,只提醒「硬缺」)· ✅ 已脚本化
- **跑法**:`python3 scripts/audit.py`(核查「待补素材」行的硬缺,输出补充清单;软缺不烦同事)。
- **触发**:状态=待补素材的行。
- **做**:逐行核查必填。分 **硬缺**(只有同事能给:材质/尺寸/隐藏款概率[仅盲盒]/系列/IP/官方依据/主图)vs **软缺**(skill 能生成:SEO/关键词/FAQ/scenario/集合)。硬缺→生成补充清单提醒同事;软缺不烦他。硬缺齐→可进 optimize。
- **铁律**:只提醒「人才能提供的」;skill 能做的绝不甩给同事。
- **责任**:skill 核查+提醒;同事补硬缺(在 01 视图)。

## 步骤 3 · `product-optimize`(生成 SEO/metafield/FAQ/集合/schema;拍板汇总问)
- **触发**:硬缺已补的行。
- **做**:① title(H1,含关键词+IP+品类)② SEO title(≤60,`X ｜ Funcinating`)/ SEO desc(≤160)③ handle 建议(英文关键词 slug)④ 主/辅关键词·搜索意图·页面角色·Schema优先级·FAQ主题 ⑤ metafields:scenario_copy · faq(**合法 json** `[{"question","answer"}]`)⑥ 集合归属建议 ⑦ **去 AI 味**(调 humanizer/humanizer-zh)⑧ 遇决策(handle 用哪个 / 集合归哪 / 术语)→ **一次性汇总给同事拍板** → 状态=待确认上线。
- **铁律**:DNT(config.dnt_names 不译)· handle 英文不译 · faq 合法 json · **非美元语言不出现 `$`**(平价框架)· 去 AI 味 · **拍板项一次问、别碎问**。
- **责任**:skill 生成;同事只拍板。

## 步骤 4 · `product-translate`(多语言,承接《多语言适配指南》)· ✅ 已脚本化(两模式)
- **跑法(两套内容,机械 bookends,中间 agent 翻)**:
  - **标准可翻译内容**(title/描述/SEO):`translate.py --entity <e> --lang <l> --export out.json` 拉 EN+digest → agent 逐条填 `target` → `--import out.json` 走 `translationsRegister` 回。
  - **`_<lang>` metafield 变体**(json/rich_text 不走标准翻译):`translate.py --entity <e> --lang <l> --export-mf mf.json` 拉 scenario_copy/faq(商品)、editorial_body/faq/homepage_*(集合)的 EN 基线 → agent 保结构翻 → `--import-mf mf.json` 走 `metafieldsSet` 写 `<key>_<lang>`(后缀见 entities.LANG_SUFFIX:es/th/zh/zh_tw)。已 E2E 验证(ZZ 测试 key 写→查→删零残留)。
- **上线前两道自检(踩过的坑,务必跑)**:
  - ★**主题 UI 完整性**:`python3 locale_check.py --pull --lang <l>`——**`--pull` 从 live 主题实拉 locale 再比**(★必须用线上真值:本地 checkout 会落后于线上、产生几百条假缺口,别信★)。揪出**缺失/还是英文的主题串**(筛选条 All/HOT/NEW、角标、header/footer/blog、aria)。★新语言最爱漏这个,店面半英半外自己看不出★。`--out gaps.json` 导缺口给 agent 翻,合并回 `<l>.json` 再 `theme publish`。DNT 专名自动过滤;剩「疑似」含同形词(Material/SKU/Global)需复核。
  - **market 启用**:`python3 translate.py --lang <l> --market-check`——**内容翻好了还得在 market 启用+发布该语言**,否则前台根本不显示(翻完纳闷「怎么没变」的坑)。
- **触发**:EN 基线定后(可与步骤 3 并行)。目标语言 = config.languages.alternates。
- **做**:从 EN 翻 title/描述/SEO → 各语言;`_<lang>` metafield 变体(scenario_copy/faq);**主题 UI 串(locale_check 揪出的)**;术语拍板(如 charm→llavero)问一次。zh-TW/th/es 批量翻,zh-CN 可同事原创。
- **铁律**:DNT/handle 不译 · **各语言共用英文 handle** · 非美元语言无 `$` · 功能词本地化 · **主题 UI 译文必须进 `locales/<lang>.json` 文件(release 会冲掉 API override)** · 上线后 **`theme publish` 清缓存**(`push` 不清)。深挖见飞书手册。
- **责任**:skill 翻;术语问同事。

## 步骤 5 · `confirm-publish`(自检→同事确认→写回+上架+索引)· ✅ 写回已脚本化
- **跑法**:`python3 scripts/sync_writeback.py [--dry-run]`(写回「待确认上线」行:productUpdate 标题/描述/SEO + metafieldsSet custom.* + 字段级 diff + handle 不写回 + **DRAFT→ACTIVE 上架** + **集合归属 collectionAddProducts** → 回填状态=已上线·写回状态·时间)。★运行本脚本=同事「确认上线」闸★。已 E2E 验证(造真草稿跑通 pull→audit→writeback→ACTIVE+集合+闭环,测后清理)。多语言写回=product-translate 步骤;GSC 索引提交仍手动/待补。
- **触发**:状态=待确认上线。
- **做**:① **自检**:必填齐 · faq 合法 json · SEO 长度 · DNT · 无 `$` · **正式列非空(★FAQ 坑:内容别只在草稿列★)** · handle 英文 ② 出「上线预检报告」③ **同事确认上线(唯一的闸)** ④ 写回 Shopify:`productUpdate`(标题/描述/seo/tags/type)+ `metafieldsSet`(custom.* + `_<lang>`)+ `translationsRegister`(各语言)+ 集合归属;**字段级 diff**(只写与线上不同的)⑤ 商品转 Active ⑥ GSC 提交索引 ⑦ 回填 `写回状态/时间`·`索引状态`·状态=`已上线`。
- **铁律**:只写同事确认的 · **handle 不写回**(改动走手动 + 301)· **正式列空不写上线** · 失败逐行记 `写回错误` 不中断 · **加商品不用 theme publish**(动主题代码才要)。
- **责任**:同事确认上线(拍板);skill 执行全部写回/上架/索引。

---

## 全局铁律(贴墙)
1. **token 绝不进文件**——Shopify 走 CLI 鉴权,Feishu 走 keychain profile。
2. **handle** 永远英文 slug,Shopify 建品时从标题自动生成并冻结;不手打、不翻译、改动补 301。
3. **专名不译(DNT)**:见 config.dnt_names。
4. **非美元语言不出现 `$`**,用平价框架。
5. **顺序**:先配齐内容+翻译+集合,最后才转 Active。
6. **json 字段(faq)必须合法**,否则 schema/前台坏。
7. **主题层改动**才需 `theme publish` 清 CDN 缓存(`theme push` 不清);单纯加商品不用。
8. **飞书表是 SSOT**:阶段用视图不拆表;实体(商品/集合/文章)各一张表。
9. **新语言别只翻商品**:主题 UI 串(locale 文件)+ market 启用是两个独立必做项——跑 `locale_check.py` + `--market-check` 自检,否则店面半英半外 / 前台压根不显示。
10. **多配送区别复制商品**:Shopify「1商品=1配送方案」,复制会变「款×2」数据乱(-TH 教训);用一方案+多仓库组。audit 会扫区域后缀警示。
11. **Judge.me 评价挂件**:用**官方挂件**(简版会空),且 app embed 的 `settings_data` 必须存进主题设置,否则 release 会剥掉挂件;改主题 `--only` 外科式推。评价按用户原文展示,不做语言适配。

## 关联
- 深挖多语言:飞书《多语言适配指南(复用手册)》
- 总纲:飞书《Shopify 独立站运营 · Skill 地图与拆解》
- 去 AI 味:`humanizer` / `humanizer-zh`
- 集合表/文章表:照本 skill 的 5 步模子复用(换实体)
