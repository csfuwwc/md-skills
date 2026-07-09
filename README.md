# md-skills

Agent Skills 合集，支持 Cursor / Claude Code 及所有兼容 [Agent Skills 规范](https://agentskills.io/specification) 的客户端。

## Skills

| Skill | 描述 |
|-------|------|
| [bilibili-keywords-scraper](skills/bilibili-keywords-scraper/) | B站关键词候选UP抓取与飞书候选池回填 |
| [douyin-scraper](skills/douyin-scraper/) | 抖音链接内容抓取与多维表格回填 |
| [weibo-scraper](skills/weibo-scraper/) | 微博链接内容抓取与多维表格回填 |
| [xiaohongshu-scraper](skills/xiaohongshu-scraper/) | 小红书内容抓取（正文/互动/元数据）与表格回填 |
| [imap-smtp-email](skills/imap-smtp-email/) | 基于 IMAP/SMTP 的收发信与附件处理（多账号） |
| [feishu-cli-manager](skills/feishu-cli-manager/) | 飞书/Lark CLI 安装、配置与授权刷新维护 |
| [video-download](skills/video-download/) | 通用社媒视频下载（抖音/小红书/B站/TikTok/YouTube 等） |
| [seedance-prompt](skills/seedance-prompt/) | 即梦 Seedance 2.0 视频脚本 Prompt 生成 |
| [skill-vetter](skills/skill-vetter/) | 第三方 Skill 安装前的安全审查与风险分级 |
| [humanizer](skills/humanizer/) | 去除英文文本的 AI 写作痕迹（基于维基百科 Signs of AI writing） |
| [humanizer-zh](skills/humanizer-zh/) | 去除中文文本的 AI 味/翻译腔（humanizer 中文版） |
| [funcinating-news](skills/funcinating-news/) | 基于新闻/话题生成 Funcinating 双语资讯（查证事实→五拍骨架→去AI味→发布到 Shopify news） |

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
`bilibili-keywords-scraper` `douyin-scraper` `weibo-scraper` `xiaohongshu-scraper` `imap-smtp-email` `feishu-cli-manager` `video-download` `seedance-prompt` `skill-vetter`

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
