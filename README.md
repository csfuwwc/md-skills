# md-skills

Agent Skills 合集，支持 Cursor / Claude Code 及所有兼容 [Agent Skills 规范](https://agentskills.io/specification) 的客户端。

## Skills

| Skill | 描述 |
|-------|------|
| [video-download](skills/video-download/) | 从抖音、小红书、B站下载视频到本地，无头浏览器后台执行 |

## 安装

### npx skills（推荐）

```bash
npx skills add https://github.com/csfuwwc/md-skills --skill video-download
```

自动安装到 `~/.cursor/skills/` 和 `~/.claude/skills/` 等目录，支持 [skills.sh](https://skills.sh/csfuwwc/md-skills/video-download) 生态。

### curl 一键安装

```bash
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- video-download
```

### 查看所有可用 skills

```bash
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- --list
```

## License

MIT
