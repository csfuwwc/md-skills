---
name: shopify
category: 范趣町业务
short-description: 范趣町 Shopify 上架流水线：内容、多语言、区域定价、履约与上线验收
description: |
  Shopify 独立站(Funcinating/范趣町)新增商品的标准上架流水线。同事只管「提供素材」,
  skill 把 SEO/handle/metafield/FAQ/集合/结构化数据/多语言/写回上架 全包,只在缺输入、
  需拍板、要确认上线时找人。6 步:sync-pull → audit → optimize → translate → regional-pricing → confirm-publish。
  上架前逐商品要求用户明确选择 CONTINUE 或 DENY,库存策略无默认值、未确认即阻断。
  确认上线时强制校验配送方案/区域运费区/线上履约仓/库存/前台真实 available,未闭环不得记成功。
  无「审核」环节——「确认上线」是唯一人工闸。飞书表=工作台+SSOT,Shopify↔飞书同步。
  与 humanizer / humanizer-zh 组合。★用前必跑 `scripts/preflight.py` 自检(config/授权/依赖应用),缺就按提示补★。业务标识读 config;token 走 keychain/.env.local 不写死。
license: MIT
---

# shopify:独立站商品上架流水线

> ⚠️ **第一步永远是自检**:`cd scripts && python3 preflight.py`。它会查 config.local.json 建了没、飞书/Shopify 授权就绪没、依赖的 Shopify 应用装了没——**没绿之前别跑后面的脚本**(脚本本身也有守卫,缺 config 会直接拦住并指回这里)。换设备/换人第一件事就是它。


**核心模型**:**同事 = 提供者 + 最终确认**;**skill = 专家,把专业活全干**。skill 只在 3 种时候找人:①缺必要输入→提醒补 ②遇决策→让拍板(含逐商品库存策略) ③全弄好→**确认上线(唯一的闸,没有独立"审核")**。

## 何时用
- 同事在 Shopify 建了草稿商品,要走完整上架(内容/SEO/GEO/多语言/集合/结构化/索引)。
- 批量补齐/优化已有商品。
- 想让「换 agent、换人」都能一致跑完上架。

## 前提(跑之前)
1. **config(必做)**:`cp config.example.json config.local.json`,在 `config.local.json` 填你的 Feishu 表 `app_token`/`table_id`(从表 URL 取;★这项不进公开仓库、只在本地;换设备各自建一份★)。运行时合并 example + local。
2. **授权**:Shopify 走 `node /home/ubuntu/fe-www.funcinating.com-next/scripts/shopify/gql.mjs`(应用凭证通道 D-011;mutation 加 --allow-mutations,绝不跑 shopify store auth);Feishu 走 `lark-cli`——**默认用你当前活动 profile(你 agent 早已登录自己的飞书,`config.feishu.profile` 留空即可,不必再写);** 只有要指定别的飞书身份时才填 profile。**任何 token 都别写进文件。** 前提:你的飞书账号得有那几张多维表格的读写权限。
3. **依赖**:`shopify` CLI、`lark-cli`、`python3`;多语言深挖见飞书《多语言适配指南(复用手册)》。

## 实体(entity)—— 一套脚本,三个资源
本 skill 用 `--entity product|collection|article` 覆盖 3 类 Shopify 资源,各自一张飞书表(config.entities),字段映射在 `scripts/entities.py`。**新增实体只在 entities.py 加一段 + config 加表**。
- `product`(商品)· `collection`(集合,editorial/faq/IP卡)· `article`(文章,news/guides)· `page`(页面,about/faq/政策/信任页)—— 均 pull→audit→writeback E2E 闭环
- 所有脚本都接 `--entity`:`sync_pull.py --entity collection` / `audit.py --entity article` / `sync_writeback.py --entity collection`。默认 product。

## 步骤 0 · `preflight`(初始化自检)· ✅ 已脚本化 —— **每次上手先跑**
- **★先问用户要哪些能力模块(onboarding 策略)★**:并非人人都动代码侧。上手时 agent **先问**:「你只做 **Shopify 后台内容**(商品/集合/文章/页面/翻译/图片/巡检),还是**也做主题 UI 多语言/前端代码侧**?」——按答案决定验哪些、引导填哪些 config,别让只做后台的同事去配前端仓。
  - **core**(默认,人人要):飞书表 + Shopify 鉴权。
  - **theme**(可选,代码侧):额外需前端仓 checkout 路径 + THEME_TOKEN(config 的 `theme` 块;不做就整块留空)。
- **跑法**:纯后台 `python3 preflight.py`;要主题 `python3 preflight.py --modules core,theme`。
- **查什么**:①`config.local.json` 建好并填了 feishu 表标识 ②**四实体表 table_id 全配**(product/collection/article/page)③飞书授权(能否读表)④Shopify 授权(能否连店)⑤**(选了 theme 才查)** 主题 `.env.local` 含 THEME_TOKEN + `locales_dir` 就绪 ⑥**列出依赖的 Shopify 应用让你确认已装**(如 Translate & Adapt;API 查不到、须人工确认,配 `config.required_apps`)。
- **缺就提示怎么补**(建 config / 跑 lark-cli auth / 配 shopify 凭证),全 ✅ 才开始 sync_pull。新设备/换人第一件事就跑它。

## 字段契约(以当前飞书表字段名为准,4 桶)
- **① 镜像**(Shopify→表,只读回填):Product ID(幂等键)· handle · 商品URL · 状态 · Vendor · Product Type · Shopify分类 · 变体/SKU/价/库存 · 主图
- **② 内容(双向)**(表内优化→确认后写回):商品名称 · 描述EN/中(**必须保存完整 HTML,含全部 `<img>`/srcset/alt,不能只存文字段**) · SEO Title/描述 EN/中 · Tags · `custom.*`(material/height/box_size/hidden_odds/series/scenario_copy/faq)· 目标IP/品类/场景集合
- **③ 规划(表内,不同步)**:IP角色 · 商品类型 · 主/辅关键词 · 搜索意图 · 页面角色 · FAQ主题 · Schema优先级 · 资料来源 · 运营优先级 · 备注。新商品先初始化为「待评估」,optimize 必须拍板为 P0/P1 或 P2,否则 QA 阻断上线。
- **④ 流程状态(表内)**:内容审核状态(状态流)· 写回状态/时间/错误 · 索引/Schema/FAQ校验状态 · 负责人 · 上线验收 · 同步日期

**状态流**:`待补素材` →(同事补硬缺)→ `待拍板` →(同事定 handle/集合/术语)→ `待确认上线` →(同事确认)→ `已上线`
**视图**:01 待补/待拍板 · 03 待确认上线 · 04 SEO-GEO 验收(索引/schema 空)

---

## 步骤 1 · `sync-pull`(拉草稿进表)· ✅ 已脚本化
- **跑法**:`cd scripts && python3 sync_pull.py [--all | --status draft | --product-id gid://shopify/Product/...] [--mirror-only] [--dry-run] [--limit N]`。默认只拉 draft;`--product-id` 精确回刷单品;`--mirror-only` 只动 Shopify 镜像、不碰内容;`--dry-run` 只显示真实字段 diff。已验证:按 Product ID 幂等 upsert、飞书记录完整翻页、镜像字段可清空旧值、内容仅填空、URL/多选/数字/日期类型感知、集合归属自动归类。
- **触发**:同事建好草稿后 / 定期。**纯读 Shopify,不回写。**
- **逻辑**:
  1. GraphQL 拉商品(默认 `query:"status:draft"`,可指定/全量):`id handle onlineStoreUrl status vendor productType tags category{fullName} title descriptionHtml seo variants(first:250){id/title/sku/price/inventoryQuantity/inventoryPolicy} featuredImage collections metafields`。Product Type/Shopify分类属于镜像;Tags 只填表内空值,不覆盖运营选择。
  2. 按 **Shopify Product ID** upsert 进飞书表(`lark-cli base +record-upsert` 或 `api ...records/batch_update`),有则更新①镜像、无则新建行。
  3. ②内容字段**仅填空、不覆盖**(不动运营已优化的)。
  4. **集合归属**写入 目标IP/品类/场景集合(★老坑:手动拉常漏集合,务必拉★)。
  5. 有真实 diff 才盖 `最近Shopify同步日期`;新草稿 `内容审核状态=待补素材`、`运营优先级=待评估`。
  6. 新建飞书行同时初始化 `Shopify写回状态=未写回`、`FAQ JSON校验状态=待检查`;`Shopify写回时间/写回错误信息` 保持空。拉取 Shopify 不是写回成功事件,不得生成时间或成功状态。
- **铁律**:幂等键=Product ID(绝不重复行)· 内容字段绝不覆盖非空 · handle 只镜像不回写 · 第二次同参数计划必须 0 写入 · 逐商品失败记录不中断。
- **验收**:每草稿一行,镜像齐、集合有、状态=待补素材,抽验与 Shopify 一致。

## 步骤 2 · `product-audit`(核查缺啥,只提醒「硬缺」)· ✅ 已脚本化
- **跑法**:`python3 scripts/audit.py`(核查「待补素材」行的硬缺,输出补充清单;软缺不烦同事)。
- **触发**:状态=待补素材的行。
- **做**:逐行核查必填。分 **硬缺**(只有同事能给:材质/尺寸/隐藏款概率[仅盲盒]/系列/IP/官方依据/主图)vs **软缺**(skill 能生成:SEO/关键词/FAQ/scenario/集合)。硬缺→生成补充清单提醒同事;软缺不烦他。硬缺齐→可进 optimize。
- **铁律**:只提醒「人才能提供的」;skill 能做的绝不甩给同事。
- **责任**:skill 核查+提醒;同事补硬缺(在 01 视图)。

## 步骤 3 · `product-optimize`(生成 SEO/metafield/FAQ/集合/schema;拍板汇总问)
- **触发**:硬缺已补的行。
- **做**:① title(H1,含关键词+IP+品类)② SEO title(≤60,`X ｜ Funcinating`)/ SEO desc(≤160)③ handle 建议(英文关键词 slug)④ 主/辅关键词·搜索意图·页面角色·Schema优先级·FAQ主题·**运营优先级(P0/P1 或 P2)** ⑤ metafields:scenario_copy · faq(**合法 json** `[{"question","answer"}]`)⑥ 集合归属建议 ⑦ **去 AI 味**(调 humanizer/humanizer-zh)⑧ 遇决策(handle 用哪个 / 集合归哪 / 术语)→ **一次性汇总给同事拍板** → 状态=待确认上线。
- **铁律**:DNT(config.dnt_names 不译)· handle 英文不译 · faq 合法 json · **非美元语言不出现 `$`**(平价框架)· 去 AI 味 · **拍板项一次问、别碎问**。
- **责任**:skill 生成;同事只拍板。

## 步骤 3.5 · `image-optimize`(正文图尺寸优化)· ✅ 已脚本化
- **跑法**:`python3 image_optimize.py --dry-run`(预览)→ `--apply`(写回)。`--handle <h>` 限单品;`--width 1600` 兜底封顶;`--no-srcset`/`--no-lazy` 退化。
- **解决**:商品描述 HTML 里的 `<img>` 常是原图直出(几 MB/张),浏览器为显示 ~750px 的图下载整张。改写正文 `<img>`:**src 加 `?width=` 封顶 + srcset 响应式 + `loading=lazy`**——手机单页正文图 ↓~45%,且懒加载让正文图不拖首屏 LCP。**纯改 descriptionHtml(productUpdate),不动 media/不重传,去 width 参数即回退。**
- **触发**:上架前 / 批量优化老商品。**图片复用**:先查是否有跨商品字节相同的图(content-length+md5),有才复用 URL、无则不折腾(art-toy 站多为专属图,常 0 命中)。
- **铁律**:只改 cdn.shopify.com 且未封顶的 `<img>`;已带 `width=` 的跳过(幂等);主图廊(media)归主题响应式、本步不碰。

## 步骤 4 · `product-translate`(多语言,承接《多语言适配指南》)· ✅ 已脚本化(两模式)
- **跑法(两套内容,机械 bookends,中间 agent 翻)**:
  - **标准可翻译内容**(title/描述/SEO):`translate.py --entity <e> --lang <l> --resource-id <gid> --export out.json` 只拉目标资源的 EN+digest → agent 逐条填 `target` → `--import out.json` 走 `translationsRegister` 回。商品 `body_html` 导入前同样执行图片门禁:禁止 Markdown 化 src/srcset,译文 `<img>` 数不得少于 EN 源。单商品上架必须传 `--resource-id`,避免误导出或处理其他商品。
  - **`_<lang>` metafield 变体**(json/rich_text 不走标准翻译):`translate.py --entity <e> --lang <l> --export-mf mf.json` 拉 scenario_copy/faq(商品)、editorial_body/faq/homepage_*(集合)的 EN 基线 → agent 保结构翻 → `--import-mf mf.json` 走 `metafieldsSet` 写 `<key>_<lang>`(后缀见 entities.LANG_SUFFIX:es/th/zh/zh_tw)。已 E2E 验证(ZZ 测试 key 写→查→删零残留)。
- **上线前两道自检(踩过的坑,务必跑)**:
  - ★**主题 UI 完整性**:`python3 locale_check.py --pull --lang <l>`——**`--pull` 从 live 主题实拉 locale 再比**(★必须用线上真值:本地 checkout 会落后于线上、产生几百条假缺口,别信★)。揪出**缺失/还是英文的主题串**(筛选条 All/HOT/NEW、角标、header/footer/blog、aria)。★新语言最爱漏这个,店面半英半外自己看不出★。`--out gaps.json` 导缺口给 agent 翻,合并回 `<l>.json` 再 `theme publish`。DNT 专名自动过滤;剩「疑似」含同形词(Material/SKU/Global)需复核。
  - **market 启用**:`python3 translate.py --lang <l> --market-check`——**内容翻好了还得在 market 启用+发布该语言**,否则前台根本不显示(翻完纳闷「怎么没变」的坑)。
- **触发**:EN 基线定后(可与步骤 3 并行)。目标语言 = config.languages.alternates。
- **做**:从 EN 翻 title/描述/SEO → 各语言;`_<lang>` metafield 变体(scenario_copy/faq);**主题 UI 串(locale_check 揪出的)**;术语拍板(如 charm→llavero)问一次。zh-TW/th/es 批量翻,zh-CN 可同事原创。
- **铁律**:DNT/handle 不译 · **各语言共用英文 handle** · 非美元语言无 `$` · 功能词本地化 · **主题 UI 译文必须进 `locales/<lang>.json` 文件(release 会冲掉 API override)** · 上线后 **`theme publish` 清缓存**(`push` 不清)。深挖见飞书手册。
- **责任**:skill 翻;术语问同事。

## 步骤 5 · `regional-pricing`(飞书矩阵定价→同档商品复核)· ✅ 已脚本化
- **位置**:翻译完成后、最终上线确认前单独执行。它不复用 `sync_writeback.py`，不改 `Product.status`，不发布商品，也不增删 Catalog 成员；商品若尚未加入任一配置目录会直接阻断，先完成目录归属再重跑。
- **跑法**:先只读预览，再明确执行：
  - `python3 scripts/regional_pricing.py --product-id 'gid://shopify/Product/...' --tier P02 --dry-run`
  - 检查 mutation plan 后：`python3 scripts/regional_pricing.py --product-id 'gid://shopify/Product/...' --tier P02 --apply`
  - 默认从 `config.pricing.reference_products` 找同档 Active 参考商品；该档未登记时必须传 `--reference-product-id 'gid://shopify/Product/...'`。
  - 变体标题/SKU 无法唯一说明包装数量时，显式重复传 `--variant-multiplier 'VARIANT_ID=N'`；不能按变体顺序猜。
  - 目标与参考商品端盒数量不同但价格档一致时，必须由同事明确确认“单盒价 × 数量”后，显式传 `--allow-reference-packaging-mismatch`。脚本仍分别按飞书单盒价校验两件商品的每个包装倍数；默认不带开关时继续阻断。
- **数值来源**:飞书价格矩阵是唯一金额 SSOT；档位必须显式是 `P01`–`P07`。不能按美元价自动推断（`P04`/`P05` 在现有目录金额相同），也不能让参考商品反向覆盖飞书。
- **标准配置**:飞书金额定义为单盒/1 Pc；整端价=`单盒价×已确认盒数`。`US-USD` 写商品基础 USD 价，US 与 Global 都必须保持继承（RELATIVE）；GB/EU/TH/SG/MY/VN/PH/ID/MX 写本币 FIXED。Catalog/PriceList 用配置中的稳定 GID 定位，标题和币种只做漂移校验；发现任何未纳入配置的新 ACTIVE Catalog 就阻断，先扩充飞书矩阵与配置。CN/BR 当前无专属 Catalog，只报 `SKIPPED_NO_CATALOG`，不得映射 Global 或自动建目录。
- **同档复核**:参考商品须为 Active；默认要求包装倍数完全一致。仅在同事明确确认“单盒价 × 数量”且显式带 `--allow-reference-packaging-mismatch` 时，允许端盒数量不同，并分别按各自倍数对飞书矩阵做归一校验。参考商品的 amount/currency/originType/Compare-at 必须与飞书矩阵和标准配置一致；漂移报 `REFERENCE_DRIFT` 并阻断，不能拿错误参考修正目标。
- **安全门禁**:只允许目标为 DRAFT；Compare-at 非空即阻断，绝不静默清除促销；写前重读飞书、目标、参考品与 Catalog/PriceList；只写 before/desired 差异；多市场中途失败自动恢复本轮已成功批次；写后全量回读，确认商品仍 DRAFT，再生成一次计划必须 0 mutation。

## 步骤 6 · `confirm-publish`(自检→同事确认→写回+上架+索引)· ✅ 写回已脚本化
- **跑法**:先执行 `python3 scripts/qa.py --entity product --status 待确认上线 --write-status`,把 FAQ 结构校验结果幂等回填飞书；全绿后可先执行 `python3 scripts/sync_writeback.py --prepare-draft --inventory-policy 'PRODUCT_ID=CONTINUE|DENY'`,将标题/描述/SEO/metafields/集合写入并保持 DRAFT，完成翻译与验收后再去掉 `--prepare-draft` 做最终激活。批量上架时每个商品重复传一次 `--inventory-policy`。第一次未传可以让脚本列出待确认商品并阻断；**不存在默认策略，也不得代替用户推断**。脚本同时执行 `config.sellability` 区域可售门禁，无需另跑手工运费检查。
- **库存策略人工闸(商品必做)**:
  1. 逐商品向用户展示当前各变体 `inventoryPolicy`，明确解释 `CONTINUE=库存为0仍可下单`、`DENY=库存为0停止销售`。
  2. 让用户逐商品二选一；不得预选、不得根据商品类型/库存/标签自动决定、不得用“推荐值”当确认。
  3. 用户未明确回答的商品不写回、不转 `ACTIVE`；脚本缺少对应 `PRODUCT_ID=...` 时整批阻断。
  4. 获得确认后，脚本用 `productVariantsBulkUpdate` 只修改与选择不一致的变体，再继续商品写回。多于 250 个变体时停止并转人工处理；写后必须回读确认每个变体都等于用户选择。
- **区域履约与前台可售门禁(商品必做)**:
  1. 从 `config.sellability.delivery_profile_id` 读取标准配送方案；确认上线后把尚未关联的目标变体用 `deliveryProfileUpdate(variantsToAssociate)` 关联进去，不按配送方案名称猜。`--dry-run` 只报告计划，不修改。
  2. 回读确认商品全部变体属于该方案；`required_country_codes` 中每个国家都有**启用运费方式 + ACTIVE 且 fulfillsOnlineOrders 的仓库**。分页超限或任一国家缺覆盖即阻断。
  3. 回读每个变体的库存地点。`DENY` 必须在对应可履约仓有正 `available`，且 `sellableOnlineQuantity>0`；`CONTINUE` 仍须存在可履约仓库存记录，不能用允许超卖掩盖错误配送关联。
  4. 商品激活后按 `storefront_checks` 读取真实区域 `/products/<handle>.js`，逐变体要求 `available=true`；Admin mutation 成功、商品有 URL、后台库存为正都不能替代这一步。允许短时重试以等待 Shopify 传播，仍为 false 就把飞书写回状态记为失败，不得记“已上线/成功”。
  5. 若后台配送/库存全部通过但前台仍 false，**禁止自动改成 CONTINUE，也禁止静默改库存**。先向用户报告；仅在用户明确确认后，才可用带 `changeFromQuantity` 和幂等键的 `inventorySetQuantities` 做 CAS 库存事件并恢复原值，随后重新验证后台与前台。
- **完整写回**:写回「待确认上线」行:标准配送方案关联 + 变体库存策略 + productUpdate 标题/描述/SEO + metafieldsSet custom.* + 字段级 diff + handle 不写回 + **DRAFT→ACTIVE 并发布到 Online Store** + **集合归属 collectionAddProducts**。**任何 Shopify mutation 之前先做两类硬闸**:①资料来源非空、运营优先级已拍板、FAQ 是非空 `[{question,answer}]` 数组；②描述禁止 `src="[URL](URL)"`/`srcset` Markdown 化,且飞书 `<img>` 数不得少于 Shopify 当前值。任一失败时整商品零 Shopify mutation,飞书记失败原因及真实 FAQ 校验状态。每个 mutation 的 `userErrors` 都是失败；全部写完必须重新读取 Shopify，核对 ACTIVE、Online Store 商品 URL、库存策略、内容、metafield、集合、区域履约和前台真实可售，并刷新飞书镜像与同步时间。只有全部回读一致才回填「已上线/成功/写回时间」并清空旧错误；任一处不一致只写「失败+错误」，绝不假绿。★运行本脚本=同事「确认上线」闸★。多语言写回=product-translate 步骤;GSC 索引提交仍手动/待补。
- **触发**:状态=待确认上线。
- **做**:① **自检**:必填齐 · faq 合法 json · SEO 长度 · DNT · 无 `$` · **正式列非空(★FAQ 坑:内容别只在草稿列★)** · handle 英文 · 运营优先级已拍板 ② 出「上线预检报告」并列出当前库存策略 ③ **同事逐商品确认 CONTINUE/DENY + 确认上线** ④ 先写用户确认的变体库存策略，再写回 Shopify:`productUpdate`(标题/描述/seo/tags/type)+ `metafieldsSet`(custom.* + `_<lang>`)+ `translationsRegister`(各语言)+ 集合归属;**字段级 diff**(只写与线上不同的)⑤ 商品转 Active ⑥ **重新读取 Shopify 验证所有目标值，并把商品URL/状态/库存/分类等镜像刷新回飞书** ⑦ 回读全绿后再回填 `写回状态/时间`·状态=`已上线`；GSC 提交与索引状态仍按独立验收处理。
- **铁律**:只写同事确认的 · **handle 不写回**(改动走手动 + 301)· **正式列空不写上线** · 失败逐行记 `写回错误` 不中断 · **加商品不用 theme publish**(动主题代码才要)。
- **责任**:同事确认上线(拍板);skill 执行全部写回/上架/索引。

---

## 巡检 · `health`(店铺健康,只读)· ✅ 已脚本化
- **跑法**:`python3 health.py`(内容)· `python3 health.py --i18n --pull`(加多语言,实拉 live locale)。
- **用途**:**常态监控,不是补缺口**——每周/每次批量改动后跑,一张报告聚合:商品 SEO/alt/集合归属/滞留草稿/正文图是否已优化 · 集合 SEO/导购正文 · 301 · 各语言 locale 完整性 + market 启用 · **飞书商品流程字段完整性**。流程巡检会抓 ACTIVE/已上线但 URL 为空、没有经回读验证的成功状态、成功无时间、失败无错误、资料来源为空、FAQ 有内容但校验未通过等矛盾。**全绿 exit 0,有待办 exit 1(可接 CI/定时)。** 只读,不改任何东西。
- 揪出的每项都指向对应修复脚本(缺翻译→translate、未优化图→image_optimize、locale 残英文→locale_check)。

## 全局铁律(贴墙)
1. **token 绝不进文件**——Shopify 走 CLI 鉴权,Feishu 走 keychain profile。
2. **handle** 永远英文 slug,Shopify 建品时从标题自动生成并冻结;不手打、不翻译、改动补 301。
3. **专名不译(DNT)**:见 config.dnt_names。
4. **非美元语言不出现 `$`**,用平价框架。
5. **顺序**:先配齐内容+翻译+集合+区域价格，最后才转 Active；区域定价未通过同档复核不得上线。
6. **json 字段(faq)必须合法**,否则 schema/前台坏。
7. **主题层改动**才需 `theme publish` 清 CDN 缓存(`theme push` 不清);单纯加商品不用。
8. **飞书表是 SSOT**:阶段用视图不拆表;实体(商品/集合/文章)各一张表。
9. **新语言别只翻商品**:主题 UI 串(locale 文件)+ market 启用是两个独立必做项——跑 `locale_check.py` + `--market-check` 自检,否则店面半英半外 / 前台压根不显示。
10. **多配送区别复制商品**:Shopify「1商品=1配送方案」,复制会变「款×2」数据乱(-TH 教训);用一方案+多仓库组。audit 会扫区域后缀警示。
11. **Judge.me 评价挂件**:用**官方挂件**(简版会空),且 app embed 的 `settings_data` 必须存进主题设置,否则 release 会剥掉挂件;改主题 `--only` 外科式推。评价按用户原文展示,不做语言适配。
12. **库存策略绝不默认**:每个待上架商品都必须由用户明确确认 `CONTINUE` 或 `DENY`;未确认即阻断,不得根据“普通商品/预售商品”等上下文替用户决定。
13. **价格档位绝不猜**:P01–P07 必须显式给出；飞书矩阵管金额、同档 Active 商品管二次校验，二者任一漂移都阻断上线。
14. **上线后必须回刷镜像**:成功标准不是 mutation 返回，而是 Shopify 回读与飞书镜像一致。历史补账用 `sync_pull.py --entity product --all --mirror-only`；它只读 Shopify，并且同参数第二次必须 0 写入。
15. **描述图片不可倒退**:`商品描述EN/中文` 存完整 HTML；历史对账时 EN 以 Shopify `descriptionHtml` 为恢复源，中文以目标 locale 前台/翻译资源为恢复源。写回前发现 Markdown 化图片地址或 `<img>` 数少于 Shopify 当前值，必须阻断，不能用纯文字版本覆盖详情图。
16. **流程状态只记已证事实**:`未写回`=没有通过当前值回读证明的成功事件；`成功`=本次写回后 Shopify 全字段回读一致；`失败`=真实执行或回读失败且必须带错误。`Shopify写回时间` 只在成功后写，`写回错误信息` 只记录真实错误。商品 `ACTIVE`、存在 URL 或 `updatedAt` 都不能反推历史写回成功/时间。历史欠账先用 `health.py` 发现，再按“Shopify 当前值对账→mutation plan→只回填有依据字段→精确回读→二次计划 0 写入”处理。
17. **后台有库存不等于区域前台可售**:上架成功必须同时证明标准配送方案关联、目标国家运费方式、线上履约仓库存、`sellableOnlineQuantity` 和区域商品 JSON `available=true`；`CONTINUE` 不能当修复手段，真实库存刷新必须另获用户确认并使用 CAS 后恢复原值。

## 关联
- 深挖多语言:飞书《多语言适配指南(复用手册)》
- 总纲:飞书《Shopify 独立站运营 · Skill 地图与拆解》
- 去 AI 味:`humanizer` / `humanizer-zh`
- 集合表/文章表:照本 skill 的内容步骤复用；区域定价仅适用于商品实体
