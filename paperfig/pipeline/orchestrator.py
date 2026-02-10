from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from paperfig.agents.architecture_critic import ArchitectureCriticAgent, report_to_dict as architecture_report_to_dict
from paperfig.agents.critic import CriticAgent
from paperfig.agents.generator import GeneratorAgent
from paperfig.agents.planner import PlannerAgent
from paperfig.audits.reproducibility import report_to_dict as repro_report_to_dict
from paperfig.audits.reproducibility import run_reproducibility_audit
from paperfig.contracts import build_figure_contract, load_contract, validate_contract_data, write_contract
from paperfig.docsgen import run_docs_regeneration
from paperfig.exporters.latex import export_latex
from paperfig.exporters.png import export_png
from paperfig.exporters.svg import export_svg
from paperfig.inspectors import build_html_inspector
from paperfig.journals import journal_profile_to_dict, load_journal_profile
from paperfig.plugins.registry import list_plugins
from paperfig.templates.loader import load_template_catalog
from paperfig.utils.config import config_hash, load_config
from paperfig.utils.pdf_parser import parse_paper
from paperfig.utils.style_refs import load_style_refs
from paperfig.utils.types import CritiqueReport, FigurePlan, JournalProfile, PaperContent


class Orchestrator:
    def __init__(
        self,
        run_root: Path = Path("runs"),
        max_iterations: int = 3,
        quality_threshold: float = 0.75,
        dimension_threshold: float = 0.55,
        template_pack: Optional[str] = None,
        arch_critique_mode: Optional[str] = None,
        arch_critique_block_severity: Optional[str] = None,
        repro_audit_mode: Optional[str] = None,
        config_path: Path = Path("paperfig.yaml"),
        journal_profile: Optional[JournalProfile] = None,
    ) -> None:
        self.run_root = run_root
        self.max_iterations = max_iterations
        self.quality_threshold = quality_threshold
        self.dimension_threshold = dimension_threshold
        self.config_path = config_path

        self.config = load_config(config_path)
        self.config_fingerprint = config_hash(self.config)

        template_cfg = self.config.get("templates", {})
        self.template_pack = template_pack or str(template_cfg.get("active_pack", "expanded_v1"))
        self.template_dir = Path(str(template_cfg.get("template_dir", "paperfig/templates/flows")))

        arch_cfg = self.config.get("architecture_critique", {})
        self.arch_critique_mode = arch_critique_mode or (
            "inline" if bool(arch_cfg.get("inline_on_generate", True)) else "off"
        )
        self.arch_critique_block_severity = arch_critique_block_severity or str(
            arch_cfg.get("block_severity", "critical")
        )
        self.arch_critique_output_file = str(arch_cfg.get("output_file", "architecture_critique.json"))

        repro_cfg = self.config.get("reproducibility", {})
        self.repro_audit_mode = repro_audit_mode or str(repro_cfg.get("mode", "soft"))
        self.repro_audit_output_file = str(repro_cfg.get("output_file", "repro_audit.json"))

        docs_cfg = self.config.get("docs", {})
        self.docs_manifest_path = Path(str(docs_cfg.get("manifest_path", "docs/docs_manifest.yaml")))
        self.docs_auto_regen_on_generate = bool(docs_cfg.get("auto_regen_on_generate", True))

        self.journal_profile = journal_profile
        if self.journal_profile:
            self.max_iterations = self.journal_profile.max_iterations
            self.quality_threshold = self.journal_profile.quality_threshold
            self.dimension_threshold = self.journal_profile.dimension_threshold
            self.arch_critique_block_severity = self.journal_profile.arch_critique_block_severity
            self.repro_audit_mode = self.journal_profile.repro_audit_mode
            if self.journal_profile.template_pack:
                self.template_pack = self.journal_profile.template_pack

        self.planner = PlannerAgent(template_dir=self.template_dir, template_pack=self.template_pack)
        self.generator = GeneratorAgent()
        self.critic = CriticAgent(
            threshold=self.quality_threshold,
            dimension_threshold=self.dimension_threshold,
        )
        self.architecture_critic = ArchitectureCriticAgent(
            repo_root=Path("."),
            template_dir=self.template_dir,
            default_template_pack=self.template_pack,
        )

    def generate(
        self,
        paper_path: Path,
        contrib: bool = False,
        _plan_override: Optional[Sequence[FigurePlan]] = None,
        _metadata_overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        paper = parse_paper(paper_path)
        plan = list(_plan_override) if _plan_override is not None else self.planner.plan(paper)
        if self.journal_profile:
            self._enforce_journal_requirements(plan)
        return self._execute_generation(
            paper_path=paper_path,
            paper=paper,
            plan=plan,
            contrib=contrib,
            metadata_overrides=_metadata_overrides,
        )

    def rerun(self, source_run_id: str, contrib: bool = False) -> str:
        source_run_dir = self.run_root / source_run_id
        if not source_run_dir.exists():
            raise FileNotFoundError(f"Run {source_run_id} not found in {self.run_root}")

        source_run_meta = self._read_json(source_run_dir / "run.json")
        if not isinstance(source_run_meta, dict):
            raise RuntimeError(f"Run {source_run_id} is missing run.json metadata.")
        paper_path = Path(str(source_run_meta.get("paper_path", "")))
        if not paper_path.exists():
            raise FileNotFoundError(f"Source paper path not found for rerun: {paper_path}")

        plan_data = self._read_json(source_run_dir / "plan.json")
        if not isinstance(plan_data, list):
            raise RuntimeError(f"Run {source_run_id} is missing a valid plan.json.")
        plan = [self._plan_from_dict(item) for item in plan_data if isinstance(item, dict)]
        if not plan:
            raise RuntimeError(f"Run {source_run_id} has an empty plan.json; cannot rerun deterministically.")

        journal_profile = None
        profile_id = source_run_meta.get("journal_profile")
        if profile_id:
            try:
                journal_profile = load_journal_profile(str(profile_id))
            except Exception:
                journal_profile = None

        replay = Orchestrator(
            run_root=self.run_root,
            max_iterations=int(source_run_meta.get("max_iterations", self.max_iterations)),
            quality_threshold=float(source_run_meta.get("quality_threshold", self.quality_threshold)),
            dimension_threshold=float(source_run_meta.get("dimension_threshold", self.dimension_threshold)),
            template_pack=str(source_run_meta.get("template_pack", self.template_pack)),
            arch_critique_mode=str(source_run_meta.get("arch_critique_mode", self.arch_critique_mode)),
            arch_critique_block_severity=str(
                source_run_meta.get("arch_critique_block_severity", self.arch_critique_block_severity)
            ),
            repro_audit_mode=str(source_run_meta.get("repro_audit_mode", self.repro_audit_mode)),
            config_path=self.config_path,
            journal_profile=journal_profile,
        )
        return replay.generate(
            paper_path=paper_path,
            contrib=contrib,
            _plan_override=plan,
            _metadata_overrides={
                "rerun_of": source_run_id,
                "reused_plan": True,
            },
        )

    def diff(self, run_id_1: str, run_id_2: str, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        run_dir_1 = self.run_root / run_id_1
        run_dir_2 = self.run_root / run_id_2
        if not run_dir_1.exists():
            raise FileNotFoundError(f"Run {run_id_1} not found in {self.run_root}")
        if not run_dir_2.exists():
            raise FileNotFoundError(f"Run {run_id_2} not found in {self.run_root}")

        inspect_1 = self._load_or_build_inspect(run_id_1)
        inspect_2 = self._load_or_build_inspect(run_id_2)
        aggregate_1 = inspect_1.get("aggregate", {})
        aggregate_2 = inspect_2.get("aggregate", {})

        metrics = {
            "accepted_count": {
                "run_1": aggregate_1.get("accepted_count"),
                "run_2": aggregate_2.get("accepted_count"),
                "delta": self._delta(aggregate_1.get("accepted_count"), aggregate_2.get("accepted_count")),
            },
            "avg_final_score": {
                "run_1": aggregate_1.get("avg_final_score"),
                "run_2": aggregate_2.get("avg_final_score"),
                "delta": self._delta(aggregate_1.get("avg_final_score"), aggregate_2.get("avg_final_score")),
            },
            "avg_traceability_coverage": {
                "run_1": aggregate_1.get("avg_traceability_coverage"),
                "run_2": aggregate_2.get("avg_traceability_coverage"),
                "delta": self._delta(
                    aggregate_1.get("avg_traceability_coverage"),
                    aggregate_2.get("avg_traceability_coverage"),
                ),
            },
        }

        changed_figures = self._diff_figures(run_id_1, inspect_1, run_id_2, inspect_2)
        changed_artifacts = self._diff_json_artifacts(run_dir_1, run_dir_2)

        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        diff_dir = output_dir or (self.run_root / "diffs" / f"diff-{run_id_1}-vs-{run_id_2}-{stamp}")
        diff_dir.mkdir(parents=True, exist_ok=True)

        report = {
            "run_id_1": run_id_1,
            "run_id_2": run_id_2,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metrics": metrics,
            "changed_figures": changed_figures,
            "changed_artifacts": changed_artifacts,
            "summary": {
                "changed_figure_count": len(changed_figures),
                "changed_artifact_count": len(changed_artifacts),
            },
            "diff_dir": str(diff_dir),
        }
        self._write_json(diff_dir / "diff.json", report)
        return report

    def regress(self, paper_v1: Path, paper_v2: Path, output_dir: Optional[Path] = None) -> Dict[str, Any]:
        run_id_v1 = self.generate(paper_v1)
        run_id_v2 = self.generate(paper_v2)

        inspect_1 = self._load_or_build_inspect(run_id_v1)
        inspect_2 = self._load_or_build_inspect(run_id_v2)
        aggregate_1 = inspect_1.get("aggregate", {})
        aggregate_2 = inspect_2.get("aggregate", {})

        metrics = {
            "accepted_count": {
                "run_1": aggregate_1.get("accepted_count"),
                "run_2": aggregate_2.get("accepted_count"),
                "delta": self._delta(aggregate_1.get("accepted_count"), aggregate_2.get("accepted_count")),
            },
            "avg_final_score": {
                "run_1": aggregate_1.get("avg_final_score"),
                "run_2": aggregate_2.get("avg_final_score"),
                "delta": self._delta(aggregate_1.get("avg_final_score"), aggregate_2.get("avg_final_score")),
            },
            "avg_traceability_coverage": {
                "run_1": aggregate_1.get("avg_traceability_coverage"),
                "run_2": aggregate_2.get("avg_traceability_coverage"),
                "delta": self._delta(
                    aggregate_1.get("avg_traceability_coverage"),
                    aggregate_2.get("avg_traceability_coverage"),
                ),
            },
        }

        invariants = [
            {
                "id": "accepted_not_decrease",
                "description": "Accepted figure count should not decrease.",
                "passed": metrics["accepted_count"]["delta"] is None or metrics["accepted_count"]["delta"] >= 0,
                "details": metrics["accepted_count"],
            },
            {
                "id": "avg_score_not_drop",
                "description": "Average final score should not drop by more than 0.05.",
                "passed": metrics["avg_final_score"]["delta"] is None or metrics["avg_final_score"]["delta"] >= -0.05,
                "details": metrics["avg_final_score"],
            },
            {
                "id": "traceability_not_drop",
                "description": "Average traceability coverage should not drop by more than 0.05.",
                "passed": metrics["avg_traceability_coverage"]["delta"] is None
                or metrics["avg_traceability_coverage"]["delta"] >= -0.05,
                "details": metrics["avg_traceability_coverage"],
            },
        ]

        diff_report = self.diff(run_id_v1, run_id_v2)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        regress_id = f"regress-{stamp}-{uuid.uuid4().hex[:6]}"
        report_dir = output_dir or (self.run_root / regress_id)
        report_dir.mkdir(parents=True, exist_ok=True)

        summary = "Regression checks passed."
        failed = [item for item in invariants if not item.get("passed")]
        if failed:
            summary = f"{len(failed)} regression invariant(s) failed."

        report = {
            "report_id": regress_id,
            "paper_v1": str(paper_v1),
            "paper_v2": str(paper_v2),
            "run_id_v1": run_id_v1,
            "run_id_v2": run_id_v2,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metrics": metrics,
            "invariants": invariants,
            "summary": summary,
            "diff_report": diff_report.get("diff_dir"),
            "report_dir": str(report_dir),
        }

        self._write_json(report_dir / "regression_report.json", report)
        return report

    def _execute_generation(
        self,
        paper_path: Path,
        paper: PaperContent,
        plan: Sequence[FigurePlan],
        contrib: bool,
        metadata_overrides: Optional[Dict[str, Any]],
    ) -> str:
        style_refs = load_style_refs()
        run_id = self._new_run_id()
        run_dir = self.run_root / run_id
        figures_dir = run_dir / "figures"
        exports_dir = run_dir / "exports"
        contrib_log_path = run_dir / "contrib.log"
        template_map = self._load_template_map()
        contract_errors: Dict[str, List[str]] = {}

        figures_dir.mkdir(parents=True, exist_ok=True)
        exports_dir.mkdir(parents=True, exist_ok=True)
        if contrib:
            self._append_contrib_log(contrib_log_path, f"start run_id={run_id} paper={paper_path}")

        self._write_run_metadata(run_dir, paper_path, extra=metadata_overrides)
        self._write_plugins_snapshot(run_dir)
        self._write_journal_profile(run_dir)
        self._write_sections(run_dir, paper)
        self._write_plan(run_dir, list(plan))
        self._write_prompts(run_dir)
        self._write_style_refs(run_dir, style_refs)
        if contrib:
            self._write_planner_notes(run_dir, list(plan))
            self._append_contrib_log(contrib_log_path, f"planner completed figures={len(plan)}")

        captions: List[str] = []
        traceability_records: List[dict] = []

        for figure_plan in plan:
            figure_dir = figures_dir / figure_plan.figure_id
            figure_dir.mkdir(parents=True, exist_ok=True)
            template = template_map.get(figure_plan.template_id)
            contract = build_figure_contract(run_id, figure_plan, template)
            write_contract(figure_dir / "contract.json", contract)
            errors = validate_contract_data(asdict(contract))
            contract_errors[figure_plan.figure_id] = errors
            if contrib and errors:
                self._append_contrib_log(
                    contrib_log_path,
                    f"contract errors figure={figure_plan.figure_id} issues={len(errors)}",
                )
            accepted = False
            last_report: CritiqueReport | None = None
            critique_feedback: dict | None = None

            for iteration in range(1, self.max_iterations + 1):
                iter_dir = figure_dir / f"iter_{iteration}"
                if contrib:
                    self._append_contrib_log(
                        contrib_log_path,
                        f"generate figure={figure_plan.figure_id} iteration={iteration}",
                    )
                candidate = self.generator.generate(
                    figure_plan,
                    paper,
                    iter_dir,
                    iteration,
                    style_refs=style_refs,
                    critique_feedback=critique_feedback,
                )
                report = self.critic.critique(Path(candidate.svg_path), figure_plan, paper)
                errors = contract_errors.get(figure_plan.figure_id, [])
                if errors:
                    self._apply_contract_validation(report, errors)
                last_report = report
                critique_feedback = {
                    "previous_score": report.score,
                    "issues": report.issues,
                    "recommendations": report.recommendations,
                    "failed_dimensions": report.failed_dimensions,
                }

                critique_path = iter_dir / "critique.json"
                with open(critique_path, "w", encoding="utf-8") as handle:
                    json.dump(asdict(report), handle, indent=2)
                if contrib:
                    self._write_critic_notes(iter_dir, report)
                    self._append_contrib_log(
                        contrib_log_path,
                        f"critique figure={figure_plan.figure_id} iteration={iteration} "
                        f"score={report.score} passed={report.passed}",
                    )

                if report.passed:
                    final_dir = figure_dir / "final"
                    final_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(candidate.svg_path, final_dir / "figure.svg")
                    shutil.copy2(candidate.element_metadata_path, final_dir / "element_metadata.json")
                    shutil.copy2(candidate.traceability_path, final_dir / "traceability.json")
                    contract_path = figure_dir / "contract.json"
                    if contract_path.exists():
                        shutil.copy2(contract_path, final_dir / "contract.json")
                    accepted = True
                    if contrib:
                        self._append_contrib_log(
                            contrib_log_path,
                            f"accepted figure={figure_plan.figure_id} iteration={iteration}",
                        )
                    break

            if not accepted and last_report:
                final_dir = figure_dir / "final"
                final_dir.mkdir(parents=True, exist_ok=True)
                # Fall back to the last iteration artifacts for traceability.
                last_iter_dir = figure_dir / f"iter_{self.max_iterations}"
                shutil.copy2(last_iter_dir / "figure.svg", final_dir / "figure.svg")
                shutil.copy2(last_iter_dir / "element_metadata.json", final_dir / "element_metadata.json")
                shutil.copy2(last_iter_dir / "traceability.json", final_dir / "traceability.json")
                contract_path = figure_dir / "contract.json"
                if contract_path.exists():
                    shutil.copy2(contract_path, final_dir / "contract.json")
                if contrib:
                    self._append_contrib_log(
                        contrib_log_path,
                        f"fallback-final figure={figure_plan.figure_id} iteration={self.max_iterations}",
                    )

            captions.append(f"{figure_plan.figure_id}: {figure_plan.title} - {figure_plan.justification}")

            traceability_path = figure_dir / "final" / "traceability.json"
            if traceability_path.exists():
                with open(traceability_path, "r", encoding="utf-8") as handle:
                    traceability_records.append(json.load(handle))

        captions_path = run_dir / "captions.txt"
        captions_path.write_text("\n".join(captions), encoding="utf-8")

        traceability_path = run_dir / "traceability.json"
        with open(traceability_path, "w", encoding="utf-8") as handle:
            json.dump({"figures": traceability_records}, handle, indent=2)

        # Finalization order: inspect -> docs check/regeneration -> architecture critique -> reproducibility audit.
        self._write_inspect_snapshot(run_id=run_id)
        if contrib:
            self._append_contrib_log(contrib_log_path, "inspect snapshot written")

        docs_report = self.docs_regenerate(check_only=not self.docs_auto_regen_on_generate)
        self._write_json(run_dir / "docs_drift_report.json", docs_report)
        if contrib:
            self._append_contrib_log(
                contrib_log_path,
                f"docs drift_detected={docs_report.get('drift_detected')}",
            )
        if docs_report.get("drift_detected"):
            raise RuntimeError(
                "Documentation drift detected and docs were regenerated. "
                "Review and commit documentation updates before rerunning."
            )

        if self.arch_critique_mode == "inline":
            architecture_report = self.critique_architecture(
                run_id,
                block_severity=self.arch_critique_block_severity,
                persist=True,
            )
            if contrib:
                self._append_contrib_log(
                    contrib_log_path,
                    f"architecture blocked={architecture_report.get('blocked')} "
                    f"findings={len(architecture_report.get('findings', []))}",
                )
            if architecture_report.get("blocked"):
                raise RuntimeError(
                    "Architecture critique blocked this run at severity threshold "
                    f"'{self.arch_critique_block_severity}'."
                )

        repro_report = self.audit(run_id, mode=self.repro_audit_mode, persist=True)
        if contrib:
            self._append_contrib_log(
                contrib_log_path,
                f"repro passed={repro_report.get('passed')} mode={self.repro_audit_mode}",
            )
        if self.repro_audit_mode == "hard" and not repro_report.get("passed", False):
            raise RuntimeError("Reproducibility audit failed in hard mode.")

        if contrib:
            self._write_contributing_notes(run_id)
            self._append_contrib_log(contrib_log_path, "contributing notes written")

        return run_id

    def docs_regenerate(
        self,
        check_only: bool = False,
        report_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        report = run_docs_regeneration(
            manifest_path=self.docs_manifest_path,
            check_only=check_only,
            repo_root=Path("."),
        )

        if report_path:
            self._write_json(report_path, report)
        return report

    def critique_architecture(
        self,
        run_id: str,
        block_severity: Optional[str] = None,
        persist: bool = True,
        enabled_rules: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        run_dir = self.run_root / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run {run_id} not found in {self.run_root}")

        threshold = block_severity or self.arch_critique_block_severity
        report_obj = self.architecture_critic.critique(
            run_dir=run_dir,
            block_severity=threshold,
            enabled_rules=enabled_rules,
        )
        report = architecture_report_to_dict(report_obj)

        if persist:
            self._write_json(run_dir / self.arch_critique_output_file, report)
        return report

    def audit(
        self,
        run_id: str,
        mode: Optional[str] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        run_dir = self.run_root / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run {run_id} not found in {self.run_root}")

        selected_mode = mode or self.repro_audit_mode
        report_obj = run_reproducibility_audit(
            run_dir=run_dir,
            mode=selected_mode,
            expected_config_hash=self.config_fingerprint,
        )
        report = repro_report_to_dict(report_obj)

        if persist:
            self._write_json(run_dir / self.repro_audit_output_file, report)
        return report

    def export(self, run_id: str, output_dir: Path | None = None) -> Path:
        run_dir = self.run_root / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run {run_id} not found in {self.run_root}")

        output_dir = output_dir or (run_dir / "exports")
        output_dir.mkdir(parents=True, exist_ok=True)
        export_report = {
            "run_id": run_id,
            "output_dir": str(output_dir),
            "figures": [],
            "warnings": [],
        }

        plan_path = run_dir / "plan.json"
        if plan_path.exists():
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            plan_by_id = {item["figure_id"]: item for item in plan_data}
        else:
            plan_by_id = {}

        figures_dir = run_dir / "figures"
        if figures_dir.exists():
            for figure_dir in figures_dir.iterdir():
                final_dir = figure_dir / "final"
                svg_path = final_dir / "figure.svg"
                if not svg_path.exists():
                    continue

                figure_id = figure_dir.name
                target_svg = output_dir / f"{figure_id}.svg"
                export_svg(svg_path, target_svg)
                figure_report = {
                    "figure_id": figure_id,
                    "svg": str(target_svg),
                    "png": None,
                    "latex": str(output_dir / f"{figure_id}.tex"),
                }

                try:
                    png_path = output_dir / f"{figure_id}.png"
                    export_png(svg_path, png_path)
                    figure_report["png"] = str(png_path)
                except RuntimeError as exc:
                    message = f"PNG export skipped for {figure_id}: {exc}"
                    if "paperfig doctor --fix png" not in message:
                        message = f"{message} Run: paperfig doctor --fix png"
                    export_report["warnings"].append(message)

                plan_entry = plan_by_id.get(figure_id, {})
                caption = plan_entry.get("title", figure_id)
                export_latex(figure_id, f"{figure_id}.svg", caption, output_dir / f"{figure_id}.tex")

                traceability_src = final_dir / "traceability.json"
                if traceability_src.exists():
                    shutil.copy2(traceability_src, output_dir / f"{figure_id}.traceability.json")

                contract_src = figure_dir / "contract.json"
                contract_payload = load_contract(contract_src) if contract_src.exists() else None
                contract_errors: List[str] = []
                if isinstance(contract_payload, dict):
                    contract_errors = validate_contract_data(contract_payload)
                else:
                    contract_errors = ["contract.json: missing or invalid"]

                figure_report["contract"] = str(contract_src) if contract_src.exists() else None
                figure_report["contract_valid"] = not contract_errors
                figure_report["contract_errors"] = contract_errors
                if contract_src.exists():
                    shutil.copy2(contract_src, output_dir / f"{figure_id}.contract.json")
                if contract_errors:
                    export_report["warnings"].append(
                        f"Contract validation failed for {figure_id}: {', '.join(contract_errors)}"
                    )
                export_report["figures"].append(figure_report)

        captions_src = run_dir / "captions.txt"
        if captions_src.exists():
            shutil.copy2(captions_src, output_dir / "captions.txt")

        traceability_src = run_dir / "traceability.json"
        if traceability_src.exists():
            shutil.copy2(traceability_src, output_dir / "traceability.json")

        with open(output_dir / "export_report.json", "w", encoding="utf-8") as handle:
            json.dump(export_report, handle, indent=2)

        return output_dir

    def inspect(
        self,
        run_id: str,
        failures_only: bool = False,
        figure_id: Optional[str] = None,
        min_score: Optional[float] = None,
        failed_dimension: Optional[str] = None,
    ) -> dict:
        run_dir = self.run_root / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run {run_id} not found in {self.run_root}")

        summary = {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "metadata": {},
            "plan_count": 0,
            "figures": [],
            "aggregate": {},
            "warnings": [],
        }

        run_meta_path = run_dir / "run.json"
        if run_meta_path.exists():
            summary["metadata"] = json.loads(run_meta_path.read_text(encoding="utf-8"))
        else:
            summary["warnings"].append("Missing run metadata: run.json")
        run_max_iterations = int(summary["metadata"].get("max_iterations", self.max_iterations))

        plan_path = run_dir / "plan.json"
        plan_by_id: dict = {}
        if plan_path.exists():
            plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
            summary["plan_count"] = len(plan_data)
            plan_by_id = {item["figure_id"]: item for item in plan_data}
        else:
            summary["warnings"].append("Missing plan: plan.json")

        figures_dir = run_dir / "figures"
        if not figures_dir.exists():
            summary["warnings"].append("Missing figures directory.")
            return summary

        figure_summaries = []
        figure_id_filter = figure_id
        for figure_dir in sorted(figures_dir.iterdir()):
            if not figure_dir.is_dir():
                continue
            current_figure_id = figure_dir.name
            plan_entry = plan_by_id.get(current_figure_id, {})

            iter_reports = []
            iter_dirs = sorted(
                [p for p in figure_dir.glob("iter_*") if p.is_dir()],
                key=lambda p: int(p.name.split("_")[1]) if "_" in p.name and p.name.split("_")[1].isdigit() else 0,
            )
            for iter_dir in iter_dirs:
                critique_path = iter_dir / "critique.json"
                if not critique_path.exists():
                    summary["warnings"].append(f"Missing critique file: {critique_path}")
                    continue
                report = json.loads(critique_path.read_text(encoding="utf-8"))
                report["iteration"] = int(iter_dir.name.split("_")[1]) if "_" in iter_dir.name else 0
                iter_reports.append(report)

            last_report = iter_reports[-1] if iter_reports else {}
            accepted = bool(last_report.get("passed", False))

            final_dir = figure_dir / "final"
            final_svg = final_dir / "figure.svg"
            element_metadata_path = final_dir / "element_metadata.json"
            traceability_path = final_dir / "traceability.json"

            total_elements = 0
            traced_elements = 0

            if element_metadata_path.exists():
                element_metadata = json.loads(element_metadata_path.read_text(encoding="utf-8"))
                if isinstance(element_metadata, list):
                    total_elements = len(element_metadata)

            if traceability_path.exists():
                traceability = json.loads(traceability_path.read_text(encoding="utf-8"))
                trace_elements = traceability.get("elements", [])
                if isinstance(trace_elements, list):
                    if total_elements == 0:
                        total_elements = len(trace_elements)
                    traced_elements = sum(
                        1 for element in trace_elements if isinstance(element.get("source_spans"), list) and element["source_spans"]
                    )

            coverage = (traced_elements / total_elements) if total_elements else None
            max_iterations_hit = bool(iter_reports) and len(iter_reports) >= run_max_iterations and not accepted

            figure_summary = {
                "figure_id": current_figure_id,
                "title": plan_entry.get("title", current_figure_id),
                "kind": plan_entry.get("kind", "unknown"),
                "template_id": plan_entry.get("template_id", ""),
                "iterations_attempted": len(iter_reports),
                "max_iterations_hit": max_iterations_hit,
                "accepted": accepted,
                "final_score": last_report.get("score"),
                "final_passed": last_report.get("passed"),
                "failed_dimensions": last_report.get("failed_dimensions", []),
                "issues": last_report.get("issues", []),
                "recommendations": last_report.get("recommendations", []),
                "traceability": {
                    "total_elements": total_elements,
                    "traced_elements": traced_elements,
                    "coverage": coverage,
                },
                "iteration_history": [
                    {
                        "iteration": report.get("iteration"),
                        "score": report.get("score"),
                        "passed": report.get("passed"),
                        "failed_dimensions": report.get("failed_dimensions", []),
                    }
                    for report in iter_reports
                ],
                "final_svg_path": str(final_svg) if final_svg.exists() else None,
            }
            figure_summaries.append(figure_summary)

        if figure_id_filter:
            figure_summaries = [item for item in figure_summaries if item.get("figure_id") == figure_id_filter]
        if failures_only:
            figure_summaries = [item for item in figure_summaries if not item.get("final_passed")]
        if min_score is not None:
            figure_summaries = [
                item
                for item in figure_summaries
                if isinstance(item.get("final_score"), (int, float)) and item["final_score"] >= min_score
            ]
        if failed_dimension:
            target = failed_dimension.strip().lower()
            figure_summaries = [
                item
                for item in figure_summaries
                if any(str(dim).lower() == target for dim in (item.get("failed_dimensions") or []))
            ]

        summary["figures"] = figure_summaries
        accepted_count = sum(1 for item in figure_summaries if item.get("final_passed"))
        total_figures = len(figure_summaries)
        final_scores = [item["final_score"] for item in figure_summaries if isinstance(item.get("final_score"), (int, float))]
        coverage_values = [
            item["traceability"]["coverage"]
            for item in figure_summaries
            if isinstance(item["traceability"].get("coverage"), (int, float))
        ]

        summary["aggregate"] = {
            "total_figures": total_figures,
            "accepted_count": accepted_count,
            "failed_count": total_figures - accepted_count,
            "avg_final_score": (sum(final_scores) / len(final_scores)) if final_scores else None,
            "avg_traceability_coverage": (sum(coverage_values) / len(coverage_values)) if coverage_values else None,
            "max_iterations_hit": [item["figure_id"] for item in figure_summaries if item.get("max_iterations_hit")],
        }

        return summary

    def inspect_html(self, run_id: str) -> Path:
        run_dir = self.run_root / run_id
        if not run_dir.exists():
            raise FileNotFoundError(f"Run {run_id} not found in {self.run_root}")
        self._load_or_build_inspect(run_id)
        manifest = build_html_inspector(run_dir, self.run_root)
        return Path(manifest.html_path)

    def _write_run_metadata(self, run_dir: Path, paper_path: Path, extra: Optional[Dict[str, Any]] = None) -> None:
        metadata = {
            "run_id": run_dir.name,
            "paper_path": str(paper_path),
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "max_iterations": self.max_iterations,
            "quality_threshold": self.quality_threshold,
            "dimension_threshold": self.dimension_threshold,
            "template_pack": self.template_pack,
            "arch_critique_mode": self.arch_critique_mode,
            "arch_critique_block_severity": self.arch_critique_block_severity,
            "repro_audit_mode": self.repro_audit_mode,
            "config_hash": self.config_fingerprint,
            "journal_profile": self.journal_profile.profile_id if self.journal_profile else None,
            "seed": None,
        }
        if extra:
            metadata.update(extra)
        self._write_json(run_dir / "run.json", metadata)

    def _write_sections(self, run_dir: Path, paper: PaperContent) -> None:
        sections = {name: asdict(section) for name, section in paper.sections.items()}
        self._write_json(run_dir / "sections.json", sections)

    def _write_plan(self, run_dir: Path, plan: List[FigurePlan]) -> None:
        self._write_json(run_dir / "plan.json", [asdict(item) for item in plan])

    def _write_prompts(self, run_dir: Path) -> None:
        prompt_dir = run_dir / "prompts"
        prompt_dir.mkdir(parents=True, exist_ok=True)
        from paperfig.utils.prompts import load_prompt

        (prompt_dir / "plan_figure.txt").write_text(load_prompt("plan_figure.txt"), encoding="utf-8")
        (prompt_dir / "critique_figure.txt").write_text(load_prompt("critique_figure.txt"), encoding="utf-8")
        try:
            (prompt_dir / "critique_architecture.txt").write_text(
                load_prompt("critique_architecture.txt"),
                encoding="utf-8",
            )
        except FileNotFoundError:
            pass
        try:
            (prompt_dir / "repro_audit.txt").write_text(
                load_prompt("repro_audit.txt"),
                encoding="utf-8",
            )
        except FileNotFoundError:
            pass

    def _write_planner_notes(self, run_dir: Path, plan: List[FigurePlan]) -> None:
        lines = [
            "# Planner Decision Notes",
            "",
            "Contributor mode is enabled for this run. Figure plan rationale:",
            "",
        ]
        for item in plan:
            lines.append(f"- `{item.figure_id}` (`{item.kind}` via `{item.template_id}`): {item.justification}")
        (run_dir / "planner_notes.md").write_text("\n".join(lines), encoding="utf-8")

    def _write_critic_notes(self, iter_dir: Path, report: CritiqueReport) -> None:
        lines = [
            "# Critic Notes",
            "",
            f"- Figure ID: `{report.figure_id}`",
            f"- Score: `{report.score}` (threshold `{report.threshold}`)",
            f"- Passed: `{report.passed}`",
            f"- Failed dimensions: {', '.join(report.failed_dimensions) if report.failed_dimensions else 'none'}",
            "",
            "## Issues",
        ]
        if report.issues:
            lines.extend([f"- {issue}" for issue in report.issues])
        else:
            lines.append("- none")
        lines.append("")
        lines.append("## Recommendations")
        if report.recommendations:
            lines.extend([f"- {item}" for item in report.recommendations])
        else:
            lines.append("- none")
        (iter_dir / "critic_notes.md").write_text("\n".join(lines), encoding="utf-8")

    def _write_contributing_notes(self, run_id: str) -> None:
        run_dir = self.run_root / run_id
        inspect_summary = self.inspect(run_id)
        aggregate = inspect_summary.get("aggregate", {})
        lines = [
            "# CONTRIBUTING NOTES",
            "",
            "This run was generated with `--contrib` mode.",
            "",
            "## Summary",
            f"- Accepted figures: {aggregate.get('accepted_count', 0)} / {aggregate.get('total_figures', 0)}",
            f"- Avg score: {aggregate.get('avg_final_score')}",
            f"- Avg traceability coverage: {aggregate.get('avg_traceability_coverage')}",
            "",
            "## How To Improve",
            "- Improve templates in `paperfig/templates/flows/*.yaml` to better match extracted sections.",
            "- Review `figures/<figure_id>/iter_*/critic_notes.md` for failed dimensions and tune prompt/style.",
            "- Add or refine architecture critique rules in `paperfig/critique/rules/`.",
            "- Run `paperfig templates lint` and `paperfig docs check` before opening a PR.",
        ]
        failed = [item for item in inspect_summary.get("figures", []) if not item.get("final_passed")]
        if failed:
            lines.append("")
            lines.append("## Failed Figures")
            for item in failed:
                lines.append(
                    f"- `{item.get('figure_id')}` score={item.get('final_score')} "
                    f"failed_dimensions={item.get('failed_dimensions')}"
                )
        (run_dir / "CONTRIBUTING_NOTES.md").write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _append_contrib_log(path: Path, message: str) -> None:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] {message}\n")

    def _apply_contract_validation(self, report: CritiqueReport, errors: List[str]) -> None:
        if not errors:
            return
        report.issues.extend([f"Contract validation failed: {error}" for error in errors])
        if "contract" not in report.failed_dimensions:
            report.failed_dimensions.append("contract")
        report.passed = False
        report.recommendations.append("Fix figure contract schema violations before rerunning critique.")

    def _load_template_map(self) -> Dict[str, object]:
        try:
            catalog = load_template_catalog(
                template_dir=self.template_dir,
                pack_id=self.template_pack,
                pack=self.template_pack,
            )
        except Exception:
            return {}
        return {template.template_id: template for template in catalog.templates}

    def _write_plugins_snapshot(self, run_dir: Path) -> None:
        descriptors = [asdict(plugin) for plugin in list_plugins()]
        self._write_json(run_dir / "plugins.json", descriptors)

    def _write_journal_profile(self, run_dir: Path) -> None:
        if not self.journal_profile:
            return
        self._write_json(run_dir / "journal_profile.json", journal_profile_to_dict(self.journal_profile))

    def _enforce_journal_requirements(self, plan: Sequence[FigurePlan]) -> None:
        if not self.journal_profile:
            return
        required = {item for item in self.journal_profile.required_kinds if item}
        present = {item.kind for item in plan}
        missing = sorted(required - present)
        if missing:
            raise RuntimeError(
                f"Journal profile '{self.journal_profile.profile_id}' requires figures: {', '.join(missing)}"
            )

    def _new_run_id(self) -> str:
        return f"run-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    def _write_style_refs(self, run_dir: Path, style_refs: dict) -> None:
        self._write_json(run_dir / "style_refs.json", style_refs)

    def _write_inspect_snapshot(self, run_id: str) -> None:
        run_dir = self.run_root / run_id
        snapshot = self.inspect(run_id)
        self._write_json(run_dir / "inspect.json", snapshot)

    def _load_or_build_inspect(self, run_id: str) -> Dict[str, Any]:
        run_dir = self.run_root / run_id
        inspect_path = run_dir / "inspect.json"
        if inspect_path.exists():
            data = self._read_json(inspect_path)
            if isinstance(data, dict):
                return data
        summary = self.inspect(run_id)
        self._write_json(inspect_path, summary)
        return summary

    def _diff_figures(
        self,
        run_id_1: str,
        inspect_1: Dict[str, Any],
        run_id_2: str,
        inspect_2: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        by_id_1 = {item.get("figure_id"): item for item in inspect_1.get("figures", [])}
        by_id_2 = {item.get("figure_id"): item for item in inspect_2.get("figures", [])}
        changed: List[Dict[str, Any]] = []

        all_ids = sorted(set(by_id_1.keys()) | set(by_id_2.keys()))
        for figure_id in all_ids:
            fig_1 = by_id_1.get(figure_id)
            fig_2 = by_id_2.get(figure_id)

            if fig_1 is None:
                changed.append({"figure_id": figure_id, "change": "added_in_run_2"})
                continue
            if fig_2 is None:
                changed.append({"figure_id": figure_id, "change": "removed_in_run_2"})
                continue

            svg_hash_1 = self._file_hash(Path(str(fig_1.get("final_svg_path")))) if fig_1.get("final_svg_path") else None
            svg_hash_2 = self._file_hash(Path(str(fig_2.get("final_svg_path")))) if fig_2.get("final_svg_path") else None

            same = (
                fig_1.get("final_score") == fig_2.get("final_score")
                and fig_1.get("final_passed") == fig_2.get("final_passed")
                and svg_hash_1 == svg_hash_2
            )
            if same:
                continue
            changed.append(
                {
                    "figure_id": figure_id,
                    "change": "modified",
                    "run_1": {
                        "final_score": fig_1.get("final_score"),
                        "final_passed": fig_1.get("final_passed"),
                        "svg_hash": svg_hash_1,
                    },
                    "run_2": {
                        "final_score": fig_2.get("final_score"),
                        "final_passed": fig_2.get("final_passed"),
                        "svg_hash": svg_hash_2,
                    },
                }
            )
        return changed

    def _diff_json_artifacts(self, run_dir_1: Path, run_dir_2: Path) -> List[str]:
        artifact_names = sorted({path.name for path in run_dir_1.glob("*.json")} | {path.name for path in run_dir_2.glob("*.json")})
        changed: List[str] = []
        for name in artifact_names:
            path_1 = run_dir_1 / name
            path_2 = run_dir_2 / name
            if path_1.exists() != path_2.exists():
                changed.append(name)
                continue
            if not path_1.exists():
                continue
            if path_1.read_text(encoding="utf-8") != path_2.read_text(encoding="utf-8"):
                changed.append(name)
        return changed

    @staticmethod
    def _delta(left: object, right: object) -> Optional[float]:
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return None
        return float(right - left)

    @staticmethod
    def _file_hash(path: Path) -> Optional[str]:
        if not path.exists():
            return None
        digest = hashlib.sha256()
        digest.update(path.read_bytes())
        return digest.hexdigest()

    @staticmethod
    def _read_json(path: Path) -> object:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _plan_from_dict(data: Dict[str, Any]) -> FigurePlan:
        return FigurePlan(
            figure_id=str(data.get("figure_id", "")),
            title=str(data.get("title", "")),
            kind=str(data.get("kind", "")),
            order=int(data.get("order", 0)),
            abstraction_level=str(data.get("abstraction_level", "medium")),
            description=str(data.get("description", "")),
            justification=str(data.get("justification", "")),
            template_id=str(data.get("template_id", "")),
            source_spans=list(data.get("source_spans", [])),
        )

    @staticmethod
    def _write_json(path: Path, data: Dict[str, Any] | List[Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
