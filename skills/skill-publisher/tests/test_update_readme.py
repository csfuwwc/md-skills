import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).parents[1] / "scripts" / "update_readme.py"
SPEC = importlib.util.spec_from_file_location("update_readme", SCRIPT)
update_readme = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_readme)


class UpdateReadmeTests(unittest.TestCase):
    def test_adds_new_skill_and_refreshes_install_name_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skills" / "existing").mkdir(parents=True)
            (root / "skills" / "new-skill" / "agents").mkdir(parents=True)
            (root / "skills" / "existing" / "SKILL.md").write_text(
                "---\nname: existing\ndescription: Existing fallback\n---\n",
                encoding="utf-8",
            )
            (root / "skills" / "new-skill" / "SKILL.md").write_text(
                "---\nname: new-skill\ndescription: New fallback description\n---\n",
                encoding="utf-8",
            )
            (root / "skills" / "new-skill" / "agents" / "openai.yaml").write_text(
                'interface:\n  short_description: "新 Skill 的简短说明"\n',
                encoding="utf-8",
            )
            readme = root / "README.md"
            readme.write_text(
                "# Skills\n\n"
                "## Skills\n\n"
                "| Skill | 描述 |\n"
                "|-------|------|\n"
                "| [existing](skills/existing/) | 保留人工描述 |\n\n"
                "## 安装\n\n"
                "可替换 `--skill` 为以下任一值：\n"
                "`existing`\n\n"
                "## License\n",
                encoding="utf-8",
            )

            changed = update_readme.update_readme(root)

            content = readme.read_text(encoding="utf-8")
            self.assertTrue(changed)
            self.assertIn(
                "| [existing](skills/existing/) | 保留人工描述 |", content
            )
            self.assertIn(
                "| [new-skill](skills/new-skill/) | 新 Skill 的简短说明 |", content
            )
            self.assertIn("`existing` `new-skill`", content)

    def test_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skills" / "only").mkdir(parents=True)
            (root / "skills" / "only" / "SKILL.md").write_text(
                "---\nname: only\ndescription: Only skill\n---\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "## Skills\n\n"
                "| Skill | 描述 |\n"
                "|-------|------|\n"
                "| [only](skills/only/) | Only skill |\n\n"
                "## 安装\n\n"
                "可替换 `--skill` 为以下任一值：\n"
                "`only`\n",
                encoding="utf-8",
            )

            self.assertFalse(update_readme.update_readme(root))

    def test_cli_refreshes_selected_existing_skill_description(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skills" / "selected").mkdir(parents=True)
            (root / "skills" / "untouched").mkdir(parents=True)
            (root / "skills" / "selected" / "SKILL.md").write_text(
                "---\nname: selected\ndescription: 复刻只有查看权限的飞书多维表格到自己的飞书。\n---\n",
                encoding="utf-8",
            )
            (root / "skills" / "untouched" / "SKILL.md").write_text(
                "---\nname: untouched\ndescription: 新的来源描述\n---\n",
                encoding="utf-8",
            )
            readme = root / "README.md"
            readme.write_text(
                "## Skills\n\n"
                "| Skill | 描述 |\n"
                "|-------|------|\n"
                "| [selected](skills/selected/) | Old English description |\n"
                "| [untouched](skills/untouched/) | 保留人工描述 |\n\n"
                "## 安装\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--refresh-skill", "selected", "--min-cjk-ratio", "0.25"],
                text=True,
                capture_output=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            content = readme.read_text(encoding="utf-8")
            self.assertIn("| [selected](skills/selected/) | 复刻只有查看权限的飞书多维表格到自己的飞书。 |", content)
            self.assertIn("| [untouched](skills/untouched/) | 保留人工描述 |", content)

    def test_cli_rejects_english_dominant_selected_description(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "skills" / "selected").mkdir(parents=True)
            (root / "skills" / "selected" / "SKILL.md").write_text(
                "---\nname: selected\ndescription: Replicate a Feishu Base with 完全复刻 support and attachment recovery.\n---\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text(
                "## Skills\n\n"
                "| Skill | 描述 |\n"
                "|-------|------|\n"
                "| [selected](skills/selected/) | Old description |\n\n"
                "## 安装\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(root), "--refresh-skill", "selected", "--min-cjk-ratio", "0.25"],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Chinese-dominant", result.stderr)


if __name__ == "__main__":
    unittest.main()
