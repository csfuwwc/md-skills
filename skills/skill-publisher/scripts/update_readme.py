#!/usr/bin/env python3
"""Synchronize the md-skills README indexes with skills/ directories."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys


ROW_RE = re.compile(
    r"^\| \[([a-z0-9-]+)\]\(skills/\1/\) \| (.*) \|$"
)
CJK_RE = re.compile(r"[\u3400-\u9fff]")
LATIN_RE = re.compile(r"[A-Za-z]")


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


def cjk_ratio(value: str) -> float:
    cjk = len(CJK_RE.findall(value))
    latin = len(LATIN_RE.findall(value))
    return cjk / (cjk + latin) if cjk + latin else 0.0


def update_readme(
    repo_root: Path,
    refresh_skills: set[str] | None = None,
    min_cjk_ratio: float = 0.0,
) -> bool:
    refresh_skills = refresh_skills or set()
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
    unknown_refresh = refresh_skills - set(skill_dirs)
    if unknown_refresh:
        raise ValueError(f"unknown refresh skills: {sorted(unknown_refresh)}")
    rows = []
    for name in ordered_names:
        if name in refresh_skills or name not in existing_descriptions:
            description = skill_description(skill_dirs[name])
        else:
            description = existing_descriptions[name]
        description = " ".join(description.split()).replace("|", "\\|")
        if name in refresh_skills and cjk_ratio(description) < min_cjk_ratio:
            raise ValueError(
                f"{name}: README description must be Chinese-dominant "
                f"(CJK ratio >= {min_cjk_ratio:.2f})"
            )
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
    parser.add_argument("--refresh-skill", action="append", default=[])
    parser.add_argument("--min-cjk-ratio", type=float, default=0.0)
    args = parser.parse_args()
    if not 0.0 <= args.min_cjk_ratio <= 1.0:
        parser.error("--min-cjk-ratio must be between 0 and 1")
    try:
        changed = update_readme(
            args.repo_root,
            refresh_skills=set(args.refresh_skill),
            min_cjk_ratio=args.min_cjk_ratio,
        )
    except ValueError as error:
        print(f"update_readme: {error}", file=sys.stderr)
        return 2
    print("README updated" if changed else "README already current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
