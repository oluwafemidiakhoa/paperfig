from __future__ import annotations

import re
import unittest
from pathlib import Path


class RenameAlignmentTests(unittest.TestCase):
    def test_pyproject_package_name_and_console_script(self) -> None:
        content = Path("pyproject.toml").read_text(encoding="utf-8")
        name_match = re.search(r'name\s*=\s*"([^"]+)"', content)
        self.assertIsNotNone(name_match, msg="Missing [project].name in pyproject.toml")
        self.assertEqual(name_match.group(1), "paperfigg")

        script_match = re.search(r'paperfig\s*=\s*"([^"]+)"', content)
        self.assertIsNotNone(script_match, msg="Missing console script for paperfig")
        self.assertEqual(script_match.group(1), "paperfig.cli:app")

    def test_readme_has_guardrail_and_correct_installs(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertRegex(
            readme,
            r"`paperfig` on PyPI is a different project; install `paperfigg`",
        )
        self.assertNotIn('pip install "paperfig"', readme)
        self.assertIn('pip install "paperfigg', readme)


if __name__ == "__main__":
    unittest.main()
