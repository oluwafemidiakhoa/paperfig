from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

from paperfig.utils.types import ReproAuditCheck


@dataclass(frozen=True)
class ReproCheckDefinition:
    check_id: str
    description: str
    required: bool
    severity: str
    evaluator: Callable[[Path, Optional[str]], ReproAuditCheck]


def _artifact_check(run_dir: Path, relative_path: str, required: bool = True) -> ReproAuditCheck:
    path = run_dir / relative_path
    exists = path.exists()
    return ReproAuditCheck(
        check_id=f"artifact_{relative_path.replace('/', '_')}",
        description=f"Artifact exists: {relative_path}",
        required=required,
        passed=exists,
        severity="major" if required else "minor",
        message="present" if exists else "missing",
        details={"path": str(path)},
    )


def _load_run_json(run_dir: Path) -> tuple[Dict[str, object], bool]:
    run_json_path = run_dir / "run.json"
    if not run_json_path.exists():
        return {}, False
    return json.loads(run_json_path.read_text(encoding="utf-8")), True


def _check_run_json_present(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    run_json_path = run_dir / "run.json"
    exists = run_json_path.exists()
    return ReproAuditCheck(
        check_id="run_json_present",
        description="Run metadata file exists",
        required=True,
        passed=exists,
        severity="critical",
        message="present" if exists else "missing",
        details={"path": str(run_json_path)},
    )


def _check_plan(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    return _artifact_check(run_dir, "plan.json", required=True)


def _check_sections(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    return _artifact_check(run_dir, "sections.json", required=True)


def _check_traceability(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    return _artifact_check(run_dir, "traceability.json", required=True)


def _check_inspect(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    return _artifact_check(run_dir, "inspect.json", required=True)


def _check_docs_drift(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    return _artifact_check(run_dir, "docs_drift_report.json", required=True)


def _check_architecture_critique(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    return _artifact_check(run_dir, "architecture_critique.json", required=True)


def _check_prompt_plan(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    return _artifact_check(run_dir, "prompts/plan_figure.txt", required=True)


def _check_prompt_critique(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    return _artifact_check(run_dir, "prompts/critique_figure.txt", required=True)


def _check_provenance(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    run_json, has_run_json = _load_run_json(run_dir)
    has_command_meta = bool(run_json.get("paper_path")) and bool(run_json.get("created_at"))
    return ReproAuditCheck(
        check_id="provenance_metadata",
        description="Run metadata captures provenance fields",
        required=True,
        passed=has_run_json and has_command_meta,
        severity="major",
        message="ok" if has_command_meta else "missing_fields",
        details={"required_fields": ["paper_path", "created_at"]},
    )


def _check_seed_declared(run_dir: Path, _: Optional[str]) -> ReproAuditCheck:
    run_json, _ = _load_run_json(run_dir)
    has_seed = "seed" in run_json
    return ReproAuditCheck(
        check_id="deterministic_seed_declared",
        description="Run metadata declares a deterministic seed",
        required=False,
        passed=has_seed,
        severity="minor",
        message="seed_present" if has_seed else "seed_missing",
        details={},
    )


def _check_config_hash(run_dir: Path, expected_config_hash: Optional[str]) -> ReproAuditCheck:
    run_json, _ = _load_run_json(run_dir)
    if expected_config_hash is None:
        return ReproAuditCheck(
            check_id="config_hash_match",
            description="Run metadata config hash matches expected hash",
            required=True,
            passed=True,
            severity="major",
            message="skipped",
            details={"expected": None, "actual": str(run_json.get("config_hash", ""))},
        )

    run_hash = str(run_json.get("config_hash", ""))
    return ReproAuditCheck(
        check_id="config_hash_match",
        description="Run metadata config hash matches expected hash",
        required=True,
        passed=(run_hash == expected_config_hash),
        severity="major",
        message="match" if run_hash == expected_config_hash else "mismatch",
        details={"expected": expected_config_hash, "actual": run_hash},
    )


def get_repro_check_registry() -> Dict[str, ReproCheckDefinition]:
    checks = [
        ReproCheckDefinition(
            check_id="run_json_present",
            description="Run metadata file exists",
            required=True,
            severity="critical",
            evaluator=_check_run_json_present,
        ),
        ReproCheckDefinition(
            check_id="plan_present",
            description="Plan artifact exists",
            required=True,
            severity="major",
            evaluator=_check_plan,
        ),
        ReproCheckDefinition(
            check_id="sections_present",
            description="Sections artifact exists",
            required=True,
            severity="major",
            evaluator=_check_sections,
        ),
        ReproCheckDefinition(
            check_id="traceability_present",
            description="Traceability artifact exists",
            required=True,
            severity="major",
            evaluator=_check_traceability,
        ),
        ReproCheckDefinition(
            check_id="inspect_present",
            description="Inspect snapshot exists",
            required=True,
            severity="major",
            evaluator=_check_inspect,
        ),
        ReproCheckDefinition(
            check_id="docs_drift_present",
            description="Docs drift report exists",
            required=True,
            severity="major",
            evaluator=_check_docs_drift,
        ),
        ReproCheckDefinition(
            check_id="architecture_critique_present",
            description="Architecture critique report exists",
            required=True,
            severity="major",
            evaluator=_check_architecture_critique,
        ),
        ReproCheckDefinition(
            check_id="prompt_plan_present",
            description="Plan prompt exists",
            required=True,
            severity="major",
            evaluator=_check_prompt_plan,
        ),
        ReproCheckDefinition(
            check_id="prompt_critique_present",
            description="Critique prompt exists",
            required=True,
            severity="major",
            evaluator=_check_prompt_critique,
        ),
        ReproCheckDefinition(
            check_id="provenance_metadata",
            description="Run metadata captures provenance fields",
            required=True,
            severity="major",
            evaluator=_check_provenance,
        ),
        ReproCheckDefinition(
            check_id="deterministic_seed_declared",
            description="Run metadata declares a deterministic seed",
            required=False,
            severity="minor",
            evaluator=_check_seed_declared,
        ),
        ReproCheckDefinition(
            check_id="config_hash_match",
            description="Run metadata config hash matches expected hash",
            required=True,
            severity="major",
            evaluator=_check_config_hash,
        ),
    ]
    return {check.check_id: check for check in checks}
