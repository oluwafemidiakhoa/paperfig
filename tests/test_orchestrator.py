from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from paperfig.pipeline.orchestrator import Orchestrator
from paperfig.journals.loader import load_journal_profile
from paperfig.utils.types import CritiqueReport, FigureCandidate, FigurePlan


class _RecordingGenerator:
    def __init__(self) -> None:
        self.calls = []

    def generate(
        self,
        plan,
        paper,
        output_dir: Path,
        iteration: int,
        style_refs=None,
        critique_feedback=None,
    ) -> FigureCandidate:
        del paper, style_refs
        output_dir.mkdir(parents=True, exist_ok=True)
        svg_path = output_dir / "figure.svg"
        element_metadata_path = output_dir / "element_metadata.json"
        traceability_path = output_dir / "traceability.json"

        svg_path.write_text("<svg><text>iter</text></svg>", encoding="utf-8")
        element_metadata_path.write_text("[]", encoding="utf-8")
        traceability_path.write_text(
            json.dumps({"figure_id": plan.figure_id, "elements": []}),
            encoding="utf-8",
        )
        self.calls.append(
            {
                "iteration": iteration,
                "critique_feedback": critique_feedback,
            }
        )
        return FigureCandidate(
            figure_id=plan.figure_id,
            svg_path=str(svg_path),
            element_metadata_path=str(element_metadata_path),
            traceability_path=str(traceability_path),
        )


class _TwoStepCritic:
    def __init__(self) -> None:
        self.calls = 0

    def critique(self, svg_path: Path, plan, paper) -> CritiqueReport:
        del svg_path, paper
        self.calls += 1
        if self.calls == 1:
            return CritiqueReport(
                figure_id=plan.figure_id,
                score=0.6,
                threshold=0.75,
                quality_dimensions={
                    "faithfulness": 0.7,
                    "readability": 0.45,
                    "conciseness": 0.7,
                    "aesthetics": 0.7,
                },
                dimension_threshold=0.55,
                failed_dimensions=["readability"],
                issues=["labels unclear"],
                recommendations=["add legend"],
                passed=False,
            )
        return CritiqueReport(
            figure_id=plan.figure_id,
            score=0.9,
            threshold=0.75,
            quality_dimensions={
                "faithfulness": 0.9,
                "readability": 0.9,
                "conciseness": 0.9,
                "aesthetics": 0.9,
            },
            dimension_threshold=0.55,
            failed_dimensions=[],
            issues=[],
            recommendations=[],
            passed=True,
        )


class _VariedCritic:
    def critique(self, svg_path: Path, plan, paper) -> CritiqueReport:
        del svg_path, paper
        if plan.kind == "results_plot":
            return CritiqueReport(
                figure_id=plan.figure_id,
                score=0.58,
                threshold=0.75,
                quality_dimensions={
                    "faithfulness": 0.85,
                    "readability": 0.82,
                    "conciseness": 0.84,
                    "aesthetics": 0.40,
                },
                dimension_threshold=0.55,
                failed_dimensions=["aesthetics"],
                issues=["Aesthetics below threshold: layout balance and presentation need refinement."],
                recommendations=["Improve alignment, spacing, and consistent visual encoding."],
                passed=False,
            )
        return CritiqueReport(
            figure_id=plan.figure_id,
            score=0.92,
            threshold=0.75,
            quality_dimensions={
                "faithfulness": 0.92,
                "readability": 0.90,
                "conciseness": 0.91,
                "aesthetics": 0.95,
            },
            dimension_threshold=0.55,
            failed_dimensions=[],
            issues=[],
            recommendations=[],
            passed=True,
        )


class _TwoFigurePlanner:
    def plan(self, paper):
        del paper
        return [
            FigurePlan(
                figure_id="fig-system",
                title="System Overview",
                kind="system_overview",
                order=1,
                abstraction_level="high",
                description="System modules and data flow.",
                justification="System section requires architecture figure.",
                source_spans=[{"section": "system", "start": 0, "end": 10, "quote": "system"}],
            ),
            FigurePlan(
                figure_id="fig-results",
                title="Results Summary",
                kind="results_plot",
                order=2,
                abstraction_level="medium",
                description="Performance metrics.",
                justification="Results section requires quantitative figure.",
                source_spans=[{"section": "results", "start": 0, "end": 10, "quote": "results"}],
            ),
        ]


class OrchestratorTests(unittest.TestCase):
    def test_generate_produces_plan_and_traceability(self) -> None:
        content = """
# Title

## Methodology
We process inputs and aggregate outputs.

## System
The system has parser, planner, generator, and critic modules.

## Results
Performance rises from 0.80 to 0.87.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                run_id = orchestrator.generate(paper)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            run_dir = runs / run_id
            self.assertTrue((run_dir / "plan.json").exists())
            self.assertTrue((run_dir / "traceability.json").exists())
            self.assertTrue((run_dir / "captions.txt").exists())
            self.assertTrue((run_dir / "inspect.json").exists())
            self.assertTrue((run_dir / "docs_drift_report.json").exists())
            self.assertTrue((run_dir / "architecture_critique.json").exists())
            self.assertTrue((run_dir / "repro_audit.json").exists())
            contracts = list((run_dir / "figures").glob("*/contract.json"))
            self.assertGreaterEqual(len(contracts), 1)
            contract_payload = json.loads(contracts[0].read_text(encoding="utf-8"))
            self.assertIn("contract_id", contract_payload)
            self.assertIn("figure_id", contract_payload)

            plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(plan), 1)

    def test_export_writes_report_and_assets(self) -> None:
        content = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                run_id = orchestrator.generate(paper)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            def _fake_export_png(svg_path: Path, png_path: Path) -> None:
                # Minimal valid PNG signature plus bytes for test artifact presence.
                png_path.parent.mkdir(parents=True, exist_ok=True)
                png_path.write_bytes(b"\x89PNG\r\n\x1a\n")

            with patch("paperfig.pipeline.orchestrator.export_png", _fake_export_png):
                out = orchestrator.export(run_id)

            self.assertTrue((out / "export_report.json").exists())
            report = json.loads((out / "export_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["warnings"], [])
            self.assertGreaterEqual(len(report["figures"]), 1)
            self.assertIn("contract_valid", report["figures"][0])

            png_files = list(out.glob("*.png"))
            self.assertGreaterEqual(len(png_files), 1)
            self.assertTrue((out / "traceability.json").exists())
            self.assertTrue((out / "captions.txt").exists())

    def test_iteration_passes_critique_feedback_to_next_generation(self) -> None:
        content = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            orchestrator = Orchestrator(run_root=runs, max_iterations=3, quality_threshold=0.75)
            recording_generator = _RecordingGenerator()
            two_step_critic = _TwoStepCritic()
            orchestrator.generator = recording_generator  # type: ignore[assignment]
            orchestrator.critic = two_step_critic  # type: ignore[assignment]

            orchestrator.generate(paper)

            self.assertGreaterEqual(len(recording_generator.calls), 2)
            self.assertIsNone(recording_generator.calls[0]["critique_feedback"])
            second_feedback = recording_generator.calls[1]["critique_feedback"]
            self.assertIsInstance(second_feedback, dict)
            self.assertEqual(second_feedback["issues"], ["labels unclear"])
            self.assertEqual(second_feedback["recommendations"], ["add legend"])

    def test_inspect_reports_iterations_and_traceability_coverage(self) -> None:
        content = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                run_id = orchestrator.generate(paper)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            summary = orchestrator.inspect(run_id)
            self.assertEqual(summary["run_id"], run_id)
            self.assertGreaterEqual(summary["plan_count"], 1)
            self.assertGreaterEqual(summary["aggregate"]["total_figures"], 1)
            first = summary["figures"][0]
            self.assertIn("iteration_history", first)
            self.assertIn("traceability", first)
            coverage = first["traceability"]["coverage"]
            self.assertTrue(coverage is None or (0.0 <= coverage <= 1.0))

            filtered_by_id = orchestrator.inspect(run_id, figure_id=first["figure_id"])
            self.assertEqual(filtered_by_id["aggregate"]["total_figures"], 1)
            self.assertEqual(filtered_by_id["figures"][0]["figure_id"], first["figure_id"])

            failures_only = orchestrator.inspect(run_id, failures_only=True)
            self.assertLessEqual(failures_only["aggregate"]["total_figures"], summary["aggregate"]["total_figures"])

    def test_inspect_filters_by_min_score_and_failed_dimension(self) -> None:
        content = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                orchestrator.planner = _TwoFigurePlanner()  # type: ignore[assignment]
                orchestrator.critic = _VariedCritic()  # type: ignore[assignment]
                run_id = orchestrator.generate(paper)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            all_summary = orchestrator.inspect(run_id)
            self.assertEqual(all_summary["aggregate"]["total_figures"], 2)

            high_score = orchestrator.inspect(run_id, min_score=0.9)
            self.assertGreaterEqual(high_score["aggregate"]["total_figures"], 1)
            for figure in high_score["figures"]:
                self.assertGreaterEqual(figure["final_score"], 0.9)

            aesthetics_failed = orchestrator.inspect(run_id, failed_dimension="aesthetics")
            self.assertGreaterEqual(aesthetics_failed["aggregate"]["total_figures"], 1)
            for figure in aesthetics_failed["figures"]:
                self.assertIn("aesthetics", [dim.lower() for dim in figure["failed_dimensions"]])

    def test_export_warning_includes_doctor_fix_hint_when_png_skipped(self) -> None:
        content = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                run_id = orchestrator.generate(paper)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            def _fake_fail_png(svg_path: Path, png_path: Path) -> None:
                del svg_path, png_path
                raise RuntimeError("cairosvg is required for PNG export. Run: paperfig doctor --fix png")

            with patch("paperfig.pipeline.orchestrator.export_png", _fake_fail_png):
                out = orchestrator.export(run_id)

            report = json.loads((out / "export_report.json").read_text(encoding="utf-8"))
            warnings = report.get("warnings", [])
            self.assertGreaterEqual(len(warnings), 1)
            self.assertTrue(any("paperfig doctor --fix png" in item for item in warnings))

    def test_rerun_and_diff_artifacts(self) -> None:
        content = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                run_id_1 = orchestrator.generate(paper)
                run_id_2 = orchestrator.rerun(run_id_1)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            self.assertNotEqual(run_id_1, run_id_2)
            run_1_plan = json.loads((runs / run_id_1 / "plan.json").read_text(encoding="utf-8"))
            run_2_plan = json.loads((runs / run_id_2 / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(run_1_plan, run_2_plan)

            rerun_meta = json.loads((runs / run_id_2 / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(rerun_meta.get("rerun_of"), run_id_1)
            self.assertTrue(rerun_meta.get("reused_plan"))

            diff_report = orchestrator.diff(run_id_1, run_id_2)
            diff_json_path = Path(diff_report["diff_dir"]) / "diff.json"
            self.assertTrue(diff_json_path.exists())
            self.assertIn("metrics", diff_report)
            self.assertIn("changed_figures", diff_report)
            self.assertIn("changed_artifacts", diff_report)

    def test_inspect_html_writes_manifest(self) -> None:
        content = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                run_id = orchestrator.generate(paper)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            html_path = orchestrator.inspect_html(run_id)
            self.assertTrue(html_path.exists())
            self.assertTrue((runs / run_id / "inspect" / "manifest.json").exists())
            self.assertIn("paperfig inspector", html_path.read_text(encoding="utf-8"))

    def test_regress_report_is_created(self) -> None:
        content_v1 = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()
        content_v2 = content_v1 + "\n\n## Results\nAdditional experiment results."

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper_v1 = tmp / "paper_v1.md"
            paper_v2 = tmp / "paper_v2.md"
            runs = tmp / "runs"
            paper_v1.write_text(content_v1, encoding="utf-8")
            paper_v2.write_text(content_v2, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                report = orchestrator.regress(paper_v1, paper_v2)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            report_dir = Path(report["report_dir"])
            self.assertTrue((report_dir / "regression_report.json").exists())
            self.assertIn("metrics", report)
            self.assertIn("invariants", report)

    def test_journal_profile_enforces_required_kinds(self) -> None:
        profile = load_journal_profile("neurips")
        content_full = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()
        content_missing = """
# Title

## Methodology
Only methodology here.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper_full = tmp / "paper_full.md"
            runs = tmp / "runs"
            paper_full.write_text(content_full, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs, journal_profile=profile)
                run_id = orchestrator.generate(paper_full)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            self.assertTrue((runs / run_id / "journal_profile.json").exists())
            run_meta = json.loads((runs / run_id / "run.json").read_text(encoding="utf-8"))
            self.assertEqual(run_meta.get("journal_profile"), profile.profile_id)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper_missing = tmp / "paper_missing.md"
            runs = tmp / "runs"
            paper_missing.write_text(content_missing, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs, journal_profile=profile)
                with self.assertRaises(RuntimeError):
                    orchestrator.generate(paper_missing)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

    def test_generate_contrib_writes_notes_and_logs(self) -> None:
        content = """
# Title

## Methodology
Method details.

## System
System details.

## Results
Result details.
""".strip()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            paper = tmp / "paper.md"
            runs = tmp / "runs"
            paper.write_text(content, encoding="utf-8")

            old_mock = os.environ.get("PAPERFIG_MOCK_PAPERBANANA")
            os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
            try:
                orchestrator = Orchestrator(run_root=runs)
                run_id = orchestrator.generate(paper, contrib=True)
            finally:
                if old_mock is None:
                    os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
                else:
                    os.environ["PAPERFIG_MOCK_PAPERBANANA"] = old_mock

            run_dir = runs / run_id
            self.assertTrue((run_dir / "CONTRIBUTING_NOTES.md").exists())
            self.assertTrue((run_dir / "planner_notes.md").exists())
            self.assertTrue((run_dir / "contrib.log").exists())
            critic_notes = list(run_dir.glob("figures/*/iter_*/critic_notes.md"))
            self.assertGreaterEqual(len(critic_notes), 1)


if __name__ == "__main__":
    unittest.main()
