from __future__ import annotations

import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from typer.testing import CliRunner
    from paperfig.cli import app
except ModuleNotFoundError:  # pragma: no cover - environment fallback
    CliRunner = None  # type: ignore[assignment]
    app = None  # type: ignore[assignment]


@unittest.skipIf(CliRunner is None or app is None, "typer is not installed in this environment")
class CliExtensionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_critique_architecture_list_rules(self) -> None:
        result = self.runner.invoke(app, ["critique-architecture", "--list-rules"])
        self.assertEqual(result.exit_code, 0, msg=result.stdout)
        self.assertIn("missing_flow_docs", result.stdout)
        self.assertIn("traceability_gap", result.stdout)
        self.assertIn("invalid_template_reference", result.stdout)

    def test_critique_architecture_enable_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            run_root = Path(tmpdir) / "runs"
            run_dir = run_root / "run-filter"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "inspect.json").write_text(
                json.dumps({"aggregate": {"failed_count": 0, "avg_traceability_coverage": 0.4}}),
                encoding="utf-8",
            )

            result = self.runner.invoke(
                app,
                [
                    "critique-architecture",
                    "run-filter",
                    "--run-root",
                    str(run_root),
                    "--enable",
                    "traceability_gap",
                    "--as-json",
                ],
            )
            self.assertEqual(result.exit_code, 0, msg=result.stdout)
            payload = json.loads(result.stdout)
            ids = {item["finding_id"] for item in payload.get("findings", [])}
            self.assertEqual(ids, {"traceability_gap"})

    def test_doctor_missing_cairosvg_shows_fix_hint(self) -> None:
        def _fake_import(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
            del args, kwargs
            if name == "cairosvg":
                raise ImportError("missing")
            return types.SimpleNamespace(__name__=name)

        with patch("paperfig.cli.importlib.import_module", side_effect=_fake_import):
            result = self.runner.invoke(app, ["doctor"])

        self.assertEqual(result.exit_code, 0, msg=result.stdout)
        self.assertIn("paperfig doctor --fix png", result.stdout)

    def test_plugins_list(self) -> None:
        result = self.runner.invoke(app, ["plugins", "list"])
        self.assertEqual(result.exit_code, 0, msg=result.stdout)
        self.assertIn("critique_rule", result.stdout)
        self.assertIn("repro_check", result.stdout)

    def test_plugins_validate(self) -> None:
        result = self.runner.invoke(app, ["plugins", "validate"])
        self.assertEqual(result.exit_code, 0, msg=result.stdout)
        self.assertIn("Plugin registry is valid", result.stdout)


if __name__ == "__main__":
    unittest.main()
