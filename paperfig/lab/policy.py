from __future__ import annotations

import shlex
from pathlib import Path
from typing import Tuple

from paperfig.lab.types import LabPolicy
from paperfig.utils.structured_data import load_structured_file


def load_policy(path: Path) -> LabPolicy:
    data = load_structured_file(path)
    if not isinstance(data, dict):
        raise RuntimeError(f"Policy file {path} must contain a mapping/object.")

    return LabPolicy(
        allowed_prefixes=[str(item) for item in data.get("allowed_prefixes", [])],
        blocked_patterns=[str(item) for item in data.get("blocked_patterns", [])],
        max_runtime_seconds=int(data.get("max_runtime_seconds", 1200)),
        max_parallel_experiments=int(data.get("max_parallel_experiments", 1)),
    )


def is_command_allowed(command: str, policy: LabPolicy) -> Tuple[bool, str]:
    lowered = command.lower()
    for pattern in policy.blocked_patterns:
        if pattern.lower() in lowered:
            return False, f"Command blocked by pattern: {pattern}"

    tokens = shlex.split(command)
    if not tokens:
        return False, "Command is empty"

    prefix = tokens[0]
    if policy.allowed_prefixes and prefix not in policy.allowed_prefixes:
        if prefix == "python" and "python3" in policy.allowed_prefixes:
            return True, "allowed (python alias for python3)"
        return False, f"Command prefix '{prefix}' is not allowed"

    return True, "allowed"
