import importlib.util
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
