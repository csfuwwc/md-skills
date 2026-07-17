#!/usr/bin/env python3
"""Synchronize the md-skills README indexes with skills/ directories."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


ROW_RE = re.compile(
    r"^\| \[([a-z0-9-]+)\]\(skills/\1/\) \| (.*) \|$"
)


def skill_description(skill_dir: Path) -> str:
    metadata = skill_dir / "agents" / "openai.yaml"
    if metadata.exists():
        match = re.search(
            r"^\s*short_description:\s*(?:\"([^\"]*)\"|'([^']*)'|(.+))\s*$",
            metadata.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        if match:
            return next(value for value in match.groups() if value is not None).strip()

    skill_md = skill_dir / "SKILL.md"
    match = re.search(
        r"^description:\s*(.+)$",
        skill_md.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1).strip().strip('"\'') if match else skill_dir.name


def update_readme(repo_root: Path) -> bool:
    readme = repo_root / "README.md"
    skills_root = repo_root / "skills"
    if not readme.exists() or not skills_root.is_dir():
        return False

    skill_dirs = {
        path.name: path
        for path in skills_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    }
    lines = readme.read_text(encoding="utf-8").splitlines()
    try:
        section_start = lines.index("## Skills")
        section_end = next(
            index
            for index in range(section_start + 1, len(lines))
            if lines[index].startswith("## ")
        )
    except (ValueError, StopIteration):
        return False

    existing_descriptions: dict[str, str] = {}
    existing_order: list[str] = []
    for line in lines[section_start + 1 : section_end]:
        match = ROW_RE.match(line)
        if match and match.group(1) in skill_dirs:
            existing_order.append(match.group(1))
            existing_descriptions[match.group(1)] = match.group(2)

    missing = sorted(set(skill_dirs) - set(existing_order))
    ordered_names = existing_order + missing
    rows = []
    for name in ordered_names:
        description = existing_descriptions.get(name) or skill_description(skill_dirs[name])
        description = " ".join(description.split()).replace("|", "\\|")
        rows.append(f"| [{name}](skills/{name}/) | {description} |")

    section = [
        "## Skills",
        "",
        "| Skill | 描述 |",
        "|-------|------|",
        *rows,
        "",
    ]
    lines[section_start:section_end] = section

    for index, line in enumerate(lines):
        if line.startswith("可替换 `--skill` 为以下任一值："):
            for candidate in range(index + 1, len(lines)):
                if lines[candidate].strip():
                    lines[candidate] = " ".join(f"`{name}`" for name in ordered_names)
                    break
            break

    updated = "\n".join(lines) + "\n"
    original = readme.read_text(encoding="utf-8")
    if updated == original:
        return False
    readme.write_text(updated, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo_root", type=Path)
    args = parser.parse_args()
    changed = update_readme(args.repo_root)
    print("README updated" if changed else "README already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
