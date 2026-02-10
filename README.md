# md-skills

Cursor Agent Skills 合集 — 一键安装，即插即用。

## 可用 Skills

| Skill | 描述 | 依赖 |
|-------|------|------|
| [video-download](skills/video-download/) | 下载抖音、小红书、B站视频到本地（无头浏览器，后台执行） | playwright, ffmpeg(B站) |

## 安装

### 方式一：远程一键安装（推荐）

无需 clone 仓库，直接指定 skill 名称安装到 `~/.cursor/skills/`：

```bash
curl -fsSL https://raw.githubusercontent.com/liyanpeng/md-skills/main/install.sh | bash -s -- video-download
```

### 方式二：本地安装

```bash
git clone https://github.com/liyanpeng/md-skills.git
cd md-skills
./install.sh video-download
```

### 查看所有可用 skills

```bash
# 远程
curl -fsSL https://raw.githubusercontent.com/liyanpeng/md-skills/main/install.sh | bash -s -- --list

# 本地
./install.sh --list
```

## 安装后

重启 Cursor，Agent 会自动识别已安装的 skills。当用户消息匹配 skill 触发条件时，Agent 会自动调用对应 skill。

## 创建新 Skill

在 `skills/` 下新建目录，包含 `SKILL.md` 即可：

```
skills/
└── your-skill-name/
    ├── SKILL.md          # 必须 - skill 定义和使用说明
    ├── scripts/          # 可选 - 脚本文件
    ├── requirements.txt  # 可选 - Python 依赖（安装时自动 pip install）
    └── setup.sh          # 可选 - 安装后自动执行的初始化脚本
```

### SKILL.md 格式

```markdown
---
name: your-skill-name
description: 简要描述。Agent 根据此描述决定何时触发 skill。
---

# Skill 标题

详细使用说明...
```

## 自定义仓库地址

远程安装时可通过环境变量指定仓库：

```bash
MD_SKILLS_OWNER=your-github-username \
MD_SKILLS_REPO=md-skills \
MD_SKILLS_BRANCH=main \
curl -fsSL https://raw.githubusercontent.com/your-github-username/md-skills/main/install.sh | bash -s -- video-download
```

## License

MIT
