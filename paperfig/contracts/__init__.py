from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from paperfig.utils.types import FigureContract, FigurePlan, FlowTemplate


SCHEMA_PATH = Path("paperfig/contracts/schema/figure_contract.schema.json")


def build_figure_contract(
    run_id: str,
    plan: FigurePlan,
    template: Optional[FlowTemplate] = None,
    schema_version: str = "1.0",
) -> FigureContract:
    required_sections: List[str] = []
    if template:
        required_sections = [str(section) for section in template.required_sections]
    else:
        required_sections = [
            str(span.get("section"))
            for span in plan.source_spans
            if isinstance(span, dict) and span.get("section")
        ]

    traceability_requirements: Dict[str, Any] = {}
    if template:
        traceability_requirements = dict(template.traceability_requirements)

    invariants = ["contract_present", "traceability_present"]
    if required_sections:
        invariants.append("required_sections_present")
    if plan.source_spans:
        invariants.append("source_spans_present")

    return FigureContract(
        contract_id=f"{run_id}:{plan.figure_id}",
        schema_version=schema_version,
        run_id=run_id,
        figure_id=plan.figure_id,
        title=plan.title,
        kind=plan.kind,
        template_id=plan.template_id,
        order=plan.order,
        abstraction_level=plan.abstraction_level,
        required_sections=required_sections,
        source_spans=list(plan.source_spans),
        traceability_requirements=traceability_requirements,
        invariants=invariants,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def load_contract_schema(schema_path: Path = SCHEMA_PATH) -> Dict[str, Any]:
    if not schema_path.exists():
        raise FileNotFoundError(f"Figure contract schema not found: {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _simple_validate(data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"{field}: is required")
    return errors


def _jsonschema_validate(data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
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


def validate_contract_data(data: Dict[str, Any], schema_path: Path = SCHEMA_PATH) -> List[str]:
    schema = load_contract_schema(schema_path=schema_path)
    return _jsonschema_validate(data, schema)


def write_contract(path: Path, contract: FigureContract) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(contract), indent=2), encoding="utf-8")


def load_contract(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
