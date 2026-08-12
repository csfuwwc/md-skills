#!/usr/bin/env python3
"""从各 SKILL.md 的 frontmatter 重新生成 README 的 skill 清单。

手维护那张表必然漂(改个名、加个 skill 就忘)。这里把 README 变成产物:
每个 skill 自己的 `category` + `description` 是事实源,README 由它们生成。

  python3 tools/gen_readme.py           写回 README.md
  python3 tools/gen_readme.py --check   只校验不改(CI / 提交前用),不一致退出码 1

新加的 skill 忘了写 category → 直接报错,不会静默漏进"未分类"。
"""
import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
README = ROOT / "README.md"
BEGIN, END = "<!-- skills:begin -->", "<!-- skills:end -->"
NAMES_BEGIN, NAMES_END = "<!-- skill-names:begin -->", "<!-- skill-names:end -->"

# 展示顺序 = 工作流顺序:看外面 → 抓回来 → 找人 → 存下来 → 做内容 → 发出去
CATEGORY_ORDER = ["情报", "内容抓取", "达人发掘", "存储与通道", "内容生产",
                  "范趣町业务", "skill 自治"]
CATEGORY_NOTE = {
    "情报": "看外面在发生什么,喂选题",
    "内容抓取": "给链接或关键词,拿回内容和数据",
    "达人发掘": "找人,不是找内容",
    "存储与通道": "东西往哪儿放、消息怎么发",
    "内容生产": "写和改",
    "范趣町业务": "**只对范趣町有意义**,换个公司用不上",
    "skill 自治": "管 skill 的 skill",
}


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not match:
        raise SystemExit(f"{path} 没有 frontmatter")
    fields, key = {}, None
    for line in match.group(1).split("\n"):
        header = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if header:
            key, value = header.group(1), header.group(2).strip()
            fields[key] = value
        elif key and line.startswith(("  ", "\t")) and not line.strip().startswith("#"):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields


def one_line(fields, limit=110):
    """优先用 short-description(人写的一句话);没有就退回截 description 并提醒补。"""
    short = fields.get("short-description")
    if short:
        return short.replace("|", "\\|")
    text = re.split(r"(?<=[。.!?])\s", fields.get("description", "").strip())[0]
    text = text.replace("|", "\\|")
    return (text if len(text) <= limit else text[:limit].rstrip() + "…") + " ⚠️缺 short-description"


def skill_names():
    return sorted(d.name for d in SKILLS_DIR.iterdir() if (d / "SKILL.md").is_file())


def render():
    grouped, problems = {}, []
    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        fields = frontmatter(skill_md)
        name = fields.get("name") or skill_dir.name
        if name != skill_dir.name:
            problems.append(f"{skill_dir.name}: frontmatter name 写的是 {name},和目录名不一致")
        category = fields.get("category")
        if not category:
            problems.append(f"{skill_dir.name}: 缺 category(可选: {', '.join(CATEGORY_ORDER)})")
            continue
        if category not in CATEGORY_ORDER:
            problems.append(f"{skill_dir.name}: 未知 category「{category}」")
            continue
        grouped.setdefault(category, []).append((skill_dir.name, one_line(fields)))
    if problems:
        raise SystemExit("README 生成失败:\n  " + "\n  ".join(problems))

    total = sum(len(v) for v in grouped.values())
    lines = [BEGIN, "", f"共 {total} 个,按在工作流里的位置分组。", ""]
    for category in CATEGORY_ORDER:
        items = grouped.get(category)
        if not items:
            continue
        lines += [f"### {category}", "", f"> {CATEGORY_NOTE[category]}", "",
                  "| Skill | 做什么 |", "|---|---|"]
        lines += [f"| [{name}](skills/{name}/) | {desc} |" for name, desc in items]
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验,不写回")
    args = parser.parse_args()

    text = README.read_text(encoding="utf-8")
    updated = text
    names_block = NAMES_BEGIN + "\n" + " ".join(f"`{n}`" for n in skill_names()) + "\n" + NAMES_END
    for begin, end, block in ((BEGIN, END, render()),
                              (NAMES_BEGIN, NAMES_END, names_block)):
        if begin not in updated or end not in updated:
            raise SystemExit(f"README 里没有 {begin} … {end} 标记,不知道该往哪儿写")
        updated = re.sub(re.escape(begin) + r".*?" + re.escape(end), lambda _: block,
                         updated, flags=re.S)

    if args.check:
        if updated != text:
            print("README 与各 SKILL.md 不一致,跑 python3 tools/gen_readme.py 重新生成", file=sys.stderr)
            return 1
        print("README 是最新的")
        return 0
    README.write_text(updated, encoding="utf-8")
    print(f"README 已更新({README})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
