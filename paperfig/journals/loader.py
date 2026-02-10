from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from paperfig.utils.structured_data import load_structured_file
from paperfig.utils.types import JournalProfile


SCHEMA_PATH = Path("paperfig/journals/schema/journal_profile.schema.json")
DOCS_SCHEMA_PATH = Path("docs/schemas/journal_profile.schema.json")
PROFILES_DIR = Path("paperfig/journals/profiles")
DOCS_PROFILES_DIR = Path("docs/journals")


def load_journal_profile(profile_id: str) -> JournalProfile:
    path = PROFILES_DIR / f"{profile_id}.json"
    if not path.exists():
        alt = DOCS_PROFILES_DIR / f"{profile_id}.json"
        if alt.exists():
            path = alt
    if not path.exists():
        raise FileNotFoundError(f"Journal profile not found: {path}")

    raw = load_structured_file(path)
    if not isinstance(raw, dict):
        raise RuntimeError(f"Journal profile {profile_id} must be a mapping/object.")

    errors = validate_journal_profile(raw)
    if errors:
        raise RuntimeError(f"Journal profile {profile_id} failed validation: {errors}")

    return JournalProfile(
        profile_id=str(raw.get("id", profile_id)),
        name=str(raw.get("name", profile_id)),
        version=str(raw.get("version", "v1")),
        quality_threshold=float(raw.get("quality_threshold", 0.8)),
        dimension_threshold=float(raw.get("dimension_threshold", 0.6)),
        max_iterations=int(raw.get("max_iterations", 3)),
        required_kinds=[str(item) for item in raw.get("required_kinds", [])],
        arch_critique_block_severity=str(raw.get("arch_critique_block_severity", "critical")),
        repro_audit_mode=str(raw.get("repro_audit_mode", "soft")),
        template_pack=str(raw.get("template_pack", "expanded_v1")),
        notes=str(raw.get("notes", "")),
    )


def validate_journal_profile(data: Dict[str, Any], schema_path: Path = SCHEMA_PATH) -> List[str]:
    schema = _load_schema(schema_path)
    return _validate_jsonschema(data, schema)


def _load_schema(path: Path) -> Dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if DOCS_SCHEMA_PATH.exists():
        return json.loads(DOCS_SCHEMA_PATH.read_text(encoding="utf-8"))
    raise FileNotFoundError(f"Journal profile schema not found: {path}")


def _simple_validate(data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"{field}: is required")
    return errors


def _validate_jsonschema(data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    try:
        from jsonschema import Draft202012Validator
    except Exception:
        return _simple_validate(data, schema)

    validator = Draft202012Validator(schema)
    errors: List[str] = []
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        field = ".".join(str(part) for part in error.path) or "<root>"
        errors.append(f"{field}: {error.message}")
    return errors


def journal_profile_to_dict(profile: JournalProfile) -> Dict[str, Any]:
    return asdict(profile)
