from __future__ import annotations

import unittest

from paperfig.plugins.registry import list_plugins, validate_plugins


class PluginTests(unittest.TestCase):
    def test_list_plugins_includes_expected_kinds(self) -> None:
        plugins = list_plugins()
        kinds = {plugin.kind for plugin in plugins}
        self.assertIn("critique_rule", kinds)
        self.assertIn("repro_check", kinds)

    def test_validate_plugins_passes(self) -> None:
        errors = validate_plugins()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
