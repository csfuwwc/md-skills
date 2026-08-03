---
name: funcinating-guides
description: 为 Funcinating(范趣町)Shopify guides 博客写「能带流量、能留人、可直接发布」的长文指南。
  模板取自 GA4 实测最优文章:流量骨架=labubu-alternatives-2026(60天浏览42,第二名5倍,蹭热词打法),
  留人要素=how-to-attach-bag-charm(人均停留72秒)。内置选题方法、结构硬规则(FAQ 必须 h3+p)、
  SEO/内链约定、写入 Shopify 与四语言流程、机器可查的验收清单。与 humanizer / humanizer-zh 组合使用。
---

# funcinating-guides:生成 Funcinating 指南长文

## 何时用

用户要写 guides 博客文章(长文指南/攻略/对比/教程),或说「按每周内容节奏出一篇 guides」。
news 短资讯不归这里,用 funcinating-news。

## 输入

- 选题(或让本 skill 按「选题方法」节提案 2-3 个供用户选)
- 目标集合/IP(内链去处,必给)

## 硬规则(违反直接作废)

1. **FAQ 结构**:FAQ 节 = `<h2>FAQ</h2>`,每组问答 = `<h3>问题?</h3><p>答案</p>`。
   **禁止** `<p><strong>问题?</strong> 答案</p>`(2026-07-11 三篇混排事故根源,已修,别再犯)。
   发布前跑体检正则(见验收节)。
2. **不渲染 metafield FAQ、不加 FAQPage schema**:owner 2026-07-09 已决定文章不展示 `custom.faq`
   且 FAQPage schema 从文章移除——别画蛇添足加回来。FAQ 就写在正文里。
3. 事实不编造:销量/价格/IP 背景查证后才写;拿不准就删掉那句。
4. IP 名(GISMOW/TARTI/CALOR/KOUCOMI/Labubu 等)保持拉丁原文,任何语言不译。
5. 链接:站内链接用相对路径且**不带国家前缀**(`/collections/gismow`);guides 文章互链用
   `/blogs/guides/{handle}`。外发推广链接才按 UTM 规范,正文内链**不加 UTM**。
6. 成稿必须过 humanizer(英文)去 AI 味;中文版过 humanizer-zh。

## 选题去重闸(动笔前必过,三道)

1. **拉现状**:`{ blogs(first:5){ nodes{ handle articles(first:50){ nodes{ handle title } } } } }`
   ——新题的核心关键词与任何既有 handle/title 重叠 → 换题或换意图(换意图须在文首规划里写明与既有篇的差异一句话)。
2. **查关键词台账**(需求侧 SSOT):飞书多维表格「【正式】Funcinating 关键词台账」
   base=`MsmGbvtMuaI9jos8y0qcItnmnif` / table=`tblu9AIxGSTVIgC8`
   (wiki: https://jcnp2psokv2t.feishu.cn/wiki/E6SWwc7mlivZd8kFcNNc1Mslnyh)。
   选题=从台账视图「02 内容机会池」(三轴状态-决策=铺新内容 且 执行阶段=待执行)里挑,
   优先级按 身份-分层(P0>P1>P1.5>P3)再叠时效性/数据动量;
   新词先入台账(词族/分层用表内既有选项)再动笔。台账候选 <6 个时按下方选题方法补一批。
3. **发布后回填**(2026-08-03 列名清理后的口径,勿用旧短名):
   - 台账该词:承接信息-承接页=相对路径(`/blogs/guides/{handle}`)、承接信息-承接类型=guides长文、
     三轴状态-执行阶段=已完成(词随即进「04 已完成监控」视图);
   - 动作表 `tblHYcmFLNHsroFx`(此表保留短名,勿改):新增一条,动作ID=`act-YYYYMMDD-{slug}`、
     动作类型=新内容、状态=已上线、词族**必须与台账该词一致**、
     基线28天指标按台账真实 GSC 值写——无曝光的假说词如实写「发文前 GSC 28 天窗口内无曝光,基线=0」,严禁编造;
   - GA4 7/14/28 天数据由周报脚本自动回填动作表,不用手动。
   文章内容与同步状态在「商品内容与SEO-GEO字段表」的 Articles 表,不在台账重复记。

## 选题方法(三类,按 GA4 已验证的优先级)

1. **蹭热词对比型(流量最大)**:`{顶流IP} alternatives`、`{顶流} vs {自家IP}`、`best {品类} {年份}`。
   范本 = labubu-alternatives-2026(蹭 Labubu 热度,60 天浏览量全站第一,site: 检索可被搜出)。
   热词从当下顶流找:Labubu/Sonny Angel/Smiski/新爆款,常换常新。
2. **实操教程型(留人最强)**:how-to 具体问题(挂件朝向/清洗保养/展示收纳)。
   范本 = how-to-attach-bag-charm(人均停留 72 秒、参与率 67%)。
3. **礼物场景型(转化导向)**:gifts under $30 / desk companions / 送礼清单,直连场景集合页。

选题自查:目标关键词有人搜吗(常识判断+顶流关联)?能自然内链到至少一个集合页吗?两个都否 = 换题。

## 结构模板(流量骨架 × 留人要素)

以 labubu-alternatives-2026 的骨架为准,揉进教程文的留人写法:

```html
<p>导语 2-3 句:直击读者痛点场景(抢不到/买贵了/摆不好),一句共情 + 一句本文承诺。
   范本口吻:"...half of them are sold out or resold at triple the price. If you're here,
   you probably want that same hit without the hunt."</p>

<h2>先解构:{热点}为什么火</h2>          <!-- 蹭词型专用;教程型换成"问题为什么会发生" -->
<p>2-3 句给读者"被理解"的感觉,顺势立起判断标准(后文推荐都围绕这几条标准)。</p>

<h2>如果你想要{需求场景A}</h2>           <!-- 每节 = 一个需求场景,对应一个自家 IP -->
<p>推荐 + 为什么符合标准 + <a href="/collections/gismow">集合内链</a>。每节配一张商品图。</p>
<h2>如果你想要{需求场景B}</h2>
<p>同上,换 IP。场景节 2-4 个,宁少勿滥。</p>
<!-- 教程型此处换成 Step 1..N:每步一个 h2、短句、具体动作、无需工具/时间承诺 -->

<h2>诚实节:{对方/现状}仍然赢在哪</h2>    <!-- 信任杠杆,labubu 文的点睛之笔,别删 -->
<p>大方承认对方优点,反而让前面的推荐可信。</p>

<h2>怎么买不挨黄牛刀</h2>               <!-- 购买引导:official/sealed/直发,内链集合 -->

<h2>FAQ</h2>                            <!-- 3-5 组,硬规则结构 -->
<h3>问题一?</h3><p>答案。</p>
<h3>问题二?</h3><p>答案。</p>
```

留人要素(修 labubu 停留仅 9 秒的短板,来自教程文):
- 首屏(导语后第一节内)就给出"本文清单预览"一句话,让扫读者知道往下有什么;
- 短句、具体名词、可执行动作;每节 ≤150 词;
- 每个场景节配图(商品图 CDN 链接),纯文字大段是跳出主因。
- **正文配图终版配方(2026-08-03 四轮排查定稿,每一条都是必要条件)**:
  ①图片先在本地裁成 **16:9 成品**(标准 1200×675;原图短边不足就用其内的 16:9 如 800×450,CDN 不放大);
  ②通过 Theme Access token 上传为**主题 asset**(`PUT themes/{live_id}/assets.json`,纯新增文件;
  别用 Files API——文件库域名的图在正文里渲染异常);
  ③写进正文必须**包在 `<p>` 里**:
  `<p><img src="https://www.funcinating.com/cdn/shop/t/1/assets/{名字}.jpg" alt="{描述}" width="1200" height="675" loading="lazy" style="max-width:100%;height:auto;border-radius:8px"></p>`
  ——裸 `<img>`(不包 p)渲染宽度会失控,这是 2026-08-03 连修四版才找到的根因;
  ④禁用 URL 动态裁剪参数(`?width=&height=&crop=`),尺寸一律在文件层面定死;
  ⑤范本=how-to-attach-bag-charm 的五张图,新文图片与它逐字节同构即正确。

篇幅:3500-5000 字符 HTML(两篇范本分别 4958/3822),别灌水到万字。

## 写入 Shopify

```graphql
# blog: guides 的 gid 现查 { blogs(first:5){ nodes{ id handle } } }
mutation { articleCreate(article: { blogId: "...", title: "...", handle: "...",
  body: "<HTML>", summary: "<meta描述,150字符内>", isPublished: false,
  author: { name: "Funcinating Team" },   # author 必填,缺了报 INVALID_VARIABLE
  tags: ["guides"], image: { url: "...", altText: "..." } }) {
  article { id } userErrors { field message } } }
```

**发布流程(2026-08-03 owner 确立,永久人工闸)**:一律先 `isPublished: false` 隐藏创建
→ 给 owner 后台预览链接(admin.shopify.com/store/qs0nxk-ft/content/articles/{id})
→ owner 确认后才 articleUpdate 置 isPublished: true,然后才做四语言与台账回填。
未确认前公开 URL 404、搜索引擎不可见。

坑(与 funcinating-news 共享):
- handle 全小写连字符英文,带年份的热词题建议 handle 也带年份(labubu-alternatives-2026);
- title ≤60 字符,把热词放最前;summary 即 meta description,写卖点不写摘要腔;
- **四语言翻译**(th/es/zh-CN/zh-TW):`translatableResource` 取 body_html digest →
  各语言 `translationsRegister`(key: title/body_html/summary_html,digest 用**当前源文的**,
  源文再改则翻译须重注册)。译文里 FAQ 结构同样必须 h3+p。

## 验收(全过才算完)

1. **FAQ 体检**(机器查,零容忍):
   `re.findall(r'<p[^>]*>\s*<strong>[^<]{5,200}[??]</strong>\s*[^<]{40,}', faq节)` 必须为空;
   `<h3>…?</h3>` 数量 = FAQ 组数。
2. humanizer 过稿(中文版 humanizer-zh);
3. 内链:≥1 个集合页链接、相对路径、无国家前缀、无 UTM;
4. 四语言注册成功且 userErrors 为空,IP 名未被翻译;
5. 发布后:GSC 对文章 URL 请求编入索引;
6. 一周后回看 GA4(pagePath 含 /blogs/guides/):浏览量、人均停留——停留 <15s 说明首屏没钩住,回炉。

## 组合与相关

- 去 AI 味:humanizer(英)/ humanizer-zh(中)
- 短资讯:funcinating-news(五拍骨架、固定信源)
- 站点约定 SSOT:飞书《Funcinating 多语言适配指南(复用手册)》、UTM 规范文档
