from __future__ import annotations

import platform
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from paperfig.audits.repro_checks import get_repro_check_registry
from paperfig.utils.types import ReproAuditReport


def run_reproducibility_audit(
    run_dir: Path,
    mode: str = "soft",
    expected_config_hash: str | None = None,
) -> ReproAuditReport:
    run_id = run_dir.name
    checks = []
    registry = get_repro_check_registry()
    for check in registry.values():
        checks.append(check.evaluator(run_dir, expected_config_hash))

    required_failed = [check for check in checks if check.required and not check.passed]
    passed = len(required_failed) == 0

    summary = "Reproducibility checks passed."
    if not passed:
        summary = f"{len(required_failed)} required reproducibility check(s) failed."

    return ReproAuditReport(
        run_id=run_id,
        mode=mode,
        checks=checks,
        passed=passed,
        summary=summary,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        environment={
            "python_version": sys.version,
            "platform": platform.platform(),
        },
    )


def report_to_dict(report: ReproAuditReport) -> Dict[str, object]:
    return asdict(report)
