---
name: skill-publisher
description: 将 ~/.agents/skills 中选定的 skill 直接发布到 GitHub 仓库，依次完成临时克隆、同步、提交、推送和自动清理。适用于“发布新 skill”、“同步更新 skill”、“按标记批量发布 skill”。支持 dry-run、按名称发布、按 .publish 标记发布、可选 prune。
---

# Skill 发布器（.agents -> GitHub）

当用户提到以下意图时必须使用本 skill：
- 发布/同步某个 skill 到 GitHub 仓库
- 把 .agents 中更新过的 skill 覆盖到开源仓库
- 批量发布带标记的 skill

## 默认约定

- 源目录：`~/.agents/skills`
- 目标仓库：`csfuwwc/md-skills`（可通过参数覆盖）
- 发布方式：临时克隆仓库后同步 `skills/` 目录、更新 README 索引、提交并推送，完成后自动删除临时目录

## 快速用法

### 1) 点名发布指定 skill

```bash
bash ./scripts/publish.sh --skills "video-download,seedance-prompt"
```

### 2) 按标记发布（推荐）

先在需要发布的 skill 目录下创建标记文件 `.publish`，再执行：

```bash
bash ./scripts/publish.sh --marked
```

### 3) 先预览变更

```bash
bash ./scripts/publish.sh --marked --dry-run
```

### 4) 同步后自动提交（不推送）

```bash
bash ./scripts/publish.sh --marked --message "chore(skills): publish updates"
```

## 行为规则

- 默认会自动提交并推送（若有变更）。
- 默认仅同步选中的 skill，不影响其他 skill。
- 发布后自动更新 README 的 Skills 表格和 `npx skills` 可选名称列表。
- 新增 skill 目录会先加入暂存区再判断差异，避免未跟踪文件被误判为“无变化”。
- 需要清理目标仓库中未选 skill 时，追加 `--prune`。
- commit 只在有变更时执行。
- 如需只本地演练不推送，使用 `--dry-run`。
