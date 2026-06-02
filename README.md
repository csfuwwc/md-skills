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

### 查看所有可用 skills

```bash
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- --list
```

## License

MIT
