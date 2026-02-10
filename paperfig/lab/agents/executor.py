from __future__ import annotations

import shlex
import subprocess
import time
import sys
from shutil import which
from typing import Tuple

from paperfig.lab.policy import is_command_allowed
from paperfig.lab.types import LabExperimentResult, LabPolicy


class LabExecutionError(RuntimeError):
    pass


def execute_command(command: str, policy: LabPolicy) -> LabExperimentResult:
    normalized_command = _normalize_command(command)
    allowed, reason = is_command_allowed(normalized_command, policy)
    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if not allowed:
        return LabExperimentResult(
            experiment_id="",
            status="failed",
            return_code=126,
            started_at=started_at,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            stdout="",
            stderr="",
            policy_violation=reason,
        )

    try:
        completed = subprocess.run(  # noqa: S603
            _command_tokens_for_exec(normalized_command),
            capture_output=True,
            text=True,
            timeout=policy.max_runtime_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return LabExperimentResult(
            experiment_id="",
            status="failed",
            return_code=124,
            started_at=started_at,
            finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            stdout=(exc.stdout or "")[:10000],
            stderr=(exc.stderr or "")[:10000],
            policy_violation="execution_timeout",
        )

    status = "completed" if completed.returncode == 0 else "failed"
    return LabExperimentResult(
        experiment_id="",
        status=status,
        return_code=completed.returncode,
        started_at=started_at,
        finished_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        stdout=completed.stdout[:10000],
        stderr=completed.stderr[:10000],
        policy_violation="",
    )


def _normalize_command(command: str) -> str:
    tokens = shlex.split(command)
    if not tokens:
        return command
    if tokens[0] == "python3" and which("python3") is None and which("python") is not None:
        tokens[0] = "python"
        return " ".join(shlex.quote(token) for token in tokens)
    return command


def _command_tokens_for_exec(command: str) -> list[str]:
    tokens = shlex.split(command)
    if not tokens:
        return tokens
    if tokens[0] in {"python", "python3"}:
        tokens[0] = sys.executable
    return tokens
