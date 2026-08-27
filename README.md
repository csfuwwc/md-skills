# md-skills

Agent Skills 合集，支持 Cursor / Claude Code 及所有兼容 [Agent Skills 规范](https://agentskills.io/specification) 的客户端。

## Skills

| Skill | 描述 |
|-------|------|
| [aihot](skills/aihot/) | 查 AI HOT 的中文 AI 资讯、热点与日报(公开只读 API,不凭记忆答新闻) |
| [hot-topics](skills/hot-topics/) | 拉微博热搜和 B 站热门榜,喂选题 |
| [douyin-scraper](skills/douyin-scraper/) | 抖音链接抓正文/互动/视觉内容,回填飞书表 |
| [tikhub-query](skills/tikhub-query/) | 走公司内部计费网关查 TikTok 视频详情 |
| [video-download](skills/video-download/) | 通用社媒视频下载(抖音/小红书/B站/TikTok/YouTube 等) |
| [wechat-scraper](skills/wechat-scraper/) | 静态优先，网关和浏览器兜底抓取公众号正文与历史文章 |
| [weibo-scraper](skills/weibo-scraper/) | 微博链接抓正文/互动/视觉内容,回填飞书表 |
| [xiaohongshu-scraper](skills/xiaohongshu-scraper/) | 小红书笔记抓正文/互动/元数据,回填飞书表 |
| [bilibili-creator-finder](skills/bilibili-creator-finder/) | 按关键词搜 B 站候选 UP 并回填飞书候选池(不发私信、不管跟进) |
| [feishu-cli-manager](skills/feishu-cli-manager/) | lark-cli 的安装、配置与授权刷新维护 |
| [imap-smtp-email](skills/imap-smtp-email/) | IMAP/SMTP 多账号收发信、附件处理与发送频率保护 |
| [oss-upload](skills/oss-upload/) | 本地图片/视频/文件传阿里云 OSS,拿可公开引用的链接 |
| [humanizer](skills/humanizer/) | 去除英文文本的 AI 写作痕迹 |
| [humanizer-zh](skills/humanizer-zh/) | 去除中文文本的 AI 味与翻译腔 |
| [seedance-prompt](skills/seedance-prompt/) | 即梦 Seedance 2.0 视频脚本 Prompt 生成 |
| [funcinating-guides](skills/funcinating-guides/) | 给范趣町 Shopify guides 写能带流量、能留人的长文指南 |
| [funcinating-news](skills/funcinating-news/) | 给范趣町 Shopify news 写双语资讯：查证、双语、SEO、轮播与发布验收 |
| [shopify](skills/shopify/) | 范趣町 Shopify 上架流水线：内容、多语言、区域定价、履约与上线验收 |
| [skill-publisher](skills/skill-publisher/) | 将 ~/.agents/skills 中选定的 skill 直接发布到 GitHub 仓库，依次完成临时克隆、同步、提交、推送和自动清理。适用于“发布新 skill”、“同步更新 skill”、“按标记批量发布 skill”。支持 dry-run、按名称发布、按 .publish 标记发布、可选 prune。 |
| [skill-vetter](skills/skill-vetter/) | 第三方 skill 安装前的安全审查与风险分级 |
| [lark-base-replica](skills/lark-base-replica/) | 复刻或迁移当前用户可合法查看但无法直接复制的飞书多维表格到自己的 Base，包含表、字段、视图、支持的普通记录和可见附件。适用于完全复刻、复制、迁移、备份或重建外部多维表格；源表保持只读，写入前必须确认精确目标 Base。 |

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
`aihot` `hot-topics` `douyin-scraper` `tikhub-query` `video-download` `wechat-scraper` `weibo-scraper` `xiaohongshu-scraper` `bilibili-creator-finder` `feishu-cli-manager` `imap-smtp-email` `oss-upload` `humanizer` `humanizer-zh` `seedance-prompt` `funcinating-guides` `funcinating-news` `shopify` `skill-publisher` `skill-vetter` `lark-base-replica`
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
