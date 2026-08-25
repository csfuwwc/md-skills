# md-skills

Agent Skills 合集，支持 Cursor / Claude Code 及所有兼容 [Agent Skills 规范](https://agentskills.io/specification) 的客户端。

## Skills

<!-- skills:begin -->

共 20 个,按在工作流里的位置分组。

### 情报

> 看外面在发生什么,喂选题

| Skill | 做什么 |
|---|---|
| [aihot](skills/aihot/) | 查 AI HOT 的中文 AI 资讯、热点与日报(公开只读 API,不凭记忆答新闻) |
| [hot-topics](skills/hot-topics/) | 拉微博热搜和 B 站热门榜,喂选题 |

### 内容抓取

> 给链接或关键词,拿回内容和数据

| Skill | 做什么 |
|---|---|
| [douyin-scraper](skills/douyin-scraper/) | 抖音链接抓正文/互动/视觉内容,回填飞书表 |
| [tikhub-query](skills/tikhub-query/) | 走公司内部计费网关查 TikTok 视频详情 |
| [video-download](skills/video-download/) | 通用社媒视频下载(抖音/小红书/B站/TikTok/YouTube 等) |
| [wechat-scraper](skills/wechat-scraper/) | 静态解析优先、网关与浏览器回退抓公众号正文及历史文章 |
| [weibo-scraper](skills/weibo-scraper/) | 微博链接抓正文/互动/视觉内容,回填飞书表 |
| [xiaohongshu-scraper](skills/xiaohongshu-scraper/) | 小红书笔记抓正文/互动/元数据,回填飞书表 |

### 达人发掘

> 找人,不是找内容

| Skill | 做什么 |
|---|---|
| [bilibili-creator-finder](skills/bilibili-creator-finder/) | 按关键词搜 B 站候选 UP 并回填飞书候选池(不发私信、不管跟进) |

### 存储与通道

> 东西往哪儿放、消息怎么发

| Skill | 做什么 |
|---|---|
| [feishu-cli-manager](skills/feishu-cli-manager/) | lark-cli 的安装、配置与授权刷新维护 |
| [imap-smtp-email](skills/imap-smtp-email/) | IMAP/SMTP 多账号收发信、附件处理与发送频率保护 |
| [oss-upload](skills/oss-upload/) | 本地图片/视频/文件传阿里云 OSS,拿可公开引用的链接 |

### 内容生产

> 写和改

| Skill | 做什么 |
|---|---|
| [humanizer](skills/humanizer/) | 去除英文文本的 AI 写作痕迹 |
| [humanizer-zh](skills/humanizer-zh/) | 去除中文文本的 AI 味与翻译腔 |
| [seedance-prompt](skills/seedance-prompt/) | 即梦 Seedance 2.0 视频脚本 Prompt 生成 |

### 范趣町业务

> **只对范趣町有意义**,换个公司用不上

| Skill | 做什么 |
|---|---|
| [funcinating-guides](skills/funcinating-guides/) | 给范趣町 Shopify guides 写能带流量、能留人的长文指南 |
| [funcinating-news](skills/funcinating-news/) | 给范趣町 Shopify news 写双语资讯：查证、双语、SEO、轮播与发布验收 |
| [shopify](skills/shopify/) | 范趣町 Shopify 上架流水线：内容、多语言、区域定价、履约与上线验收 |

### skill 自治

> 管 skill 的 skill

| Skill | 做什么 |
|---|---|
| [skill-publisher](skills/skill-publisher/) | 把本机选定的 skill 发布同步到 GitHub 仓库 |
| [skill-vetter](skills/skill-vetter/) | 第三方 skill 安装前的安全审查与风险分级 |

<!-- skills:end -->

> 这张表由 `python3 tools/gen_readme.py` 从各 `SKILL.md` 的 frontmatter 生成,**别手改**。
> 加了新 skill 就跑一次;`--check` 可在提交前校验是否漂了。

## 安装

### Agent 安装（推荐）

把想安装的 skill 名称和链接发给 Agent：

```text
帮我安装 skill video-download：https://github.com/csfuwwc/md-skills/tree/main/skills/video-download
```

也可以换成其他 skill：

```text
帮我安装 skill feishu-cli-manager：https://github.com/csfuwwc/md-skills/tree/main/skills/feishu-cli-manager
```

如果是按飞书 CLI 官方文档里的 Agent 安装方式，也可以直接把文档链接交给 Agent：

```text
帮我安装飞书 CLI：https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md
```

### npx skills（手动）

```bash
npx skills add https://github.com/csfuwwc/md-skills --skill douyin-scraper
```

自动安装到 `~/.cursor/skills/` 和 `~/.claude/skills/` 等目录，支持 [skills.sh](https://skills.sh/csfuwwc/md-skills/video-download) 生态。

可替换 `--skill` 为以下任一值：
<!-- skill-names:begin -->
`aihot` `bilibili-creator-finder` `douyin-scraper` `feishu-cli-manager` `funcinating-guides` `funcinating-news` `hot-topics` `humanizer` `humanizer-zh` `imap-smtp-email` `oss-upload` `seedance-prompt` `shopify` `skill-publisher` `skill-vetter` `tikhub-query` `video-download` `wechat-scraper` `weibo-scraper` `xiaohongshu-scraper`
<!-- skill-names:end -->

### curl 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- douyin-scraper
```

## feishu-cli-manager

`feishu-cli-manager` 用来让 Agent 帮你安装、配置和维护飞书/Lark CLI。安装 skill 后，直接对 Agent 说：

```text
帮我安装飞书 CLI：https://open.feishu.cn/document/no_class/mcp-archive/feishu-cli-installation-guide.md
```

或：

```text
用 feishu-cli-manager 帮我安装飞书 CLI，并完成配置和登录检查
```

如果你想自己处理终端交互，也可以手动执行官方入口：

```sh
npx @larksuite/cli@latest install
```

### 查看所有可用 skills

```bash
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- --list
```

## License

MIT
