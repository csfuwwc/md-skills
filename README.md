# md-skills

Cursor Agent Skills 合集 — 一键安装，即插即用。兼容 [Agent Skills 开放规范](https://agentskills.io/specification)。

## 可用 Skills

| Skill | 描述 | 依赖 |
|-------|------|------|
| [video-download](skills/video-download/) | 下载抖音、小红书、B站视频到本地（无头浏览器，后台执行） | playwright, ffmpeg(B站) |

## 安装

### 方式一：npx skills（推荐，兼容 skills.sh 生态）

兼容 [skills.sh](https://skills.sh/) 生态，支持 Cursor / Copilot CLI / Claude Code / Gemini CLI 等多客户端：

```bash
npx skills add https://github.com/csfuwwc/md-skills --skill video-download
```

### 方式二：curl 一键安装（零依赖）

无需 Node.js，只需 bash + curl：

```bash
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- video-download
```

### 方式三：本地安装

```bash
git clone https://github.com/csfuwwc/md-skills.git
cd md-skills
./install.sh video-download
```

### 查看所有可用 skills

```bash
# 远程
curl -fsSL https://raw.githubusercontent.com/csfuwwc/md-skills/main/install.sh | bash -s -- --list

# 本地
./install.sh --list
```

## 安装后

重启 Cursor，Agent 会自动识别已安装的 skills。当用户消息匹配 skill 触发条件时，Agent 会自动调用对应 skill。

## 创建新 Skill

在 `skills/` 下新建目录，包含 `SKILL.md` 即可。格式遵循 [Agent Skills 规范](https://agentskills.io/specification)：

```
skills/
└── your-skill-name/
    ├── SKILL.md          # 必须 - skill 定义和使用说明
    ├── scripts/          # 可选 - 可执行脚本
    ├── references/       # 可选 - 补充文档
    ├── assets/           # 可选 - 静态资源（模板、图片等）
    ├── requirements.txt  # 可选 - Python 依赖（install.sh 安装时自动 pip install）
    └── setup.sh          # 可选 - 安装后自动执行的初始化脚本
```

### SKILL.md 格式

```markdown
---
name: your-skill-name
description: 简要描述。Agent 根据此描述决定何时触发 skill。包含关键词帮助 Agent 识别相关任务。
---

# Skill 标题

详细使用说明...
```

**注意：**
- `name` 只能用小写字母、数字和连字符（`a-z`, `0-9`, `-`），且必须与目录名一致
- `description` 尽量详细，包含触发关键词，Agent 依靠它决定是否激活 skill

## 自定义仓库地址

curl 方式安装时可通过环境变量指定仓库：

```bash
MD_SKILLS_OWNER=your-github-username \
MD_SKILLS_REPO=md-skills \
MD_SKILLS_BRANCH=main \
curl -fsSL https://raw.githubusercontent.com/your-github-username/md-skills/main/install.sh | bash -s -- video-download
```

## License

MIT
