from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

from paperfig.plugins.registry import resolve_enabled_critique_plugins
from paperfig.critique.rules.base import RuleContext
from paperfig.templates.loader import load_template_catalog
from paperfig.utils.prompts import load_prompt
from paperfig.utils.types import ArchitectureCritiqueReport


SEVERITY_ORDER = {
    "info": 0,
    "minor": 1,
    "major": 2,
    "critical": 3,
}


class ArchitectureCriticAgent:
    def __init__(
        self,
        repo_root: Path = Path("."),
        template_dir: Path = Path("paperfig/templates/flows"),
        default_template_pack: str = "expanded_v1",
    ) -> None:
        self.prompt = load_prompt("critique_architecture.txt")
        self.repo_root = repo_root
        self.template_dir = template_dir
        self.default_template_pack = default_template_pack

    def available_rules(self) -> List[dict]:
        rules = resolve_enabled_critique_plugins(None)
        return [
            {
                "rule_id": plugin.descriptor.plugin_id.split(".", 1)[-1],
                "description": plugin.descriptor.description,
            }
            for plugin in rules
        ]

    def critique(
        self,
        run_dir: Path,
        block_severity: str = "critical",
        enabled_rules: Optional[Sequence[str]] = None,
    ) -> ArchitectureCritiqueReport:
        run_id = run_dir.name

        run_metadata = self._read_json(run_dir / "run.json")
        inspect_data = self._read_json(run_dir / "inspect.json")
        plan_data = self._read_json(run_dir / "plan.json")
        docs_drift_report = self._read_json(run_dir / "docs_drift_report.json")

        valid_template_ids = self._resolve_valid_template_ids(run_metadata)
        context = RuleContext(
            run_dir=run_dir,
            repo_root=self.repo_root,
            run_metadata=run_metadata if isinstance(run_metadata, dict) else {},
            inspect_data=inspect_data if isinstance(inspect_data, dict) else None,
            plan_data=plan_data if isinstance(plan_data, list) else None,
            docs_drift_report=docs_drift_report if isinstance(docs_drift_report, dict) else None,
            valid_template_ids=valid_template_ids,
        )

        findings = []
        for plugin in resolve_enabled_critique_plugins(enabled_rules):
            findings.extend(plugin.evaluator(context))

        max_seen = max((SEVERITY_ORDER.get(item.severity, 0) for item in findings), default=0)
        blocked = max_seen >= SEVERITY_ORDER.get(block_severity, SEVERITY_ORDER["critical"])

        summary = "No architecture findings."
        if findings:
            summary = f"{len(findings)} finding(s); highest severity={self._severity_name(max_seen)}"

        return ArchitectureCritiqueReport(
            run_id=run_id,
            block_severity=block_severity,
            findings=list(findings),
            blocked=blocked,
            summary=summary,
            generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

    def _resolve_valid_template_ids(self, run_metadata: object) -> Set[str]:
        if not isinstance(run_metadata, dict):
            return set()

        template_pack = str(run_metadata.get("template_pack", self.default_template_pack))
        try:
            catalog = load_template_catalog(
                template_dir=self.template_dir,
                pack_id=template_pack,
                pack=template_pack,
            )
        except Exception:
            return set()
        return {template.template_id for template in catalog.templates}

    @staticmethod
    def _read_json(path: Path) -> object:
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _severity_name(value: int) -> str:
        for name, rank in SEVERITY_ORDER.items():
            if rank == value:
                return name
        return "info"


def report_to_dict(report: ArchitectureCritiqueReport) -> Dict[str, object]:
    return asdict(report)
