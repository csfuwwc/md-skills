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

## 安装

### npx skills（推荐）

```bash
npx skills add https://github.com/csfuwwc/md-skills --skill douyin-scraper
```

自动安装到 `~/.cursor/skills/` 和 `~/.claude/skills/` 等目录，支持 [skills.sh](https://skills.sh/csfuwwc/md-skills/video-download) 生态。

可替换 `--skill` 为以下任一值：
`bilibili-keywords-scraper` `douyin-scraper` `weibo-scraper` `xiaohongshu-scraper` `imap-smtp-email` `feishu-cli-manager` `video-download` `seedance-prompt`

### curl 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- douyin-scraper
```

## feishu-cli-manager

`feishu-cli-manager` 用来让 Agent 帮你安装、配置和维护飞书/Lark CLI。参考飞书 CLI 官方文档，建议优先采用 Agent 安装方式；只有在你想自己控制每一步终端操作时，再使用手动安装。

### 安装 skill

```bash
npx skills add https://github.com/csfuwwc/md-skills --skill feishu-cli-manager
```

### Agent 安装飞书 CLI（推荐）

安装 skill 后，直接对 Agent 说：

```text
用 feishu-cli-manager 帮我安装飞书 CLI，并完成配置和登录检查
```

Agent 会按实际环境检查 Node.js、npm、`lark-cli` 是否已存在；缺失时再执行官方安装入口：

```bash
npx @larksuite/cli@latest install
```

随后根据环境继续处理：

```bash
lark-cli config init --new
lark-cli auth login --recommend
lark-cli auth status
```

如果 CLI 输出授权链接，Agent 需要把链接原样给你，由你在浏览器里完成授权。

### 手动安装飞书 CLI

如果不想让 Agent 代执行，可以自己在终端运行：

```bash
npx @larksuite/cli@latest install
lark-cli config init --new
lark-cli auth login --recommend
lark-cli auth status
```

手动安装适合你想自己处理浏览器授权、终端交互和配置选择的情况。若遇到 `keychain not initialized`，先换到有本机钥匙串访问权限的终端重试，不要直接判断为飞书账号失效。

### 查看所有可用 skills

```bash
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- --list
```

## License

MIT
