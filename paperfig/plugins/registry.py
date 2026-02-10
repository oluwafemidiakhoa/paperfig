from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from paperfig.critique.rules import get_rule_registry
from paperfig.audits.repro_checks import get_repro_check_registry
from paperfig.plugins.base import CritiqueRulePlugin, ReproCheckPlugin
from paperfig.utils.types import PluginDescriptor


SCHEMA_PATH = Path("paperfig/plugins/schema/plugin_descriptor.schema.json")


def list_plugins(kind: Optional[str] = None) -> List[PluginDescriptor]:
    descriptors = [plugin.descriptor for plugin in _critique_plugins()]
    descriptors.extend([plugin.descriptor for plugin in _repro_plugins()])
    if kind:
        return [descriptor for descriptor in descriptors if descriptor.kind == kind]
    return sorted(descriptors, key=lambda item: (item.kind, item.plugin_id))


def validate_plugins(kind: Optional[str] = None) -> List[str]:
    descriptors = list_plugins(kind=kind)
    if not descriptors:
        return ["<registry>: no plugins found"]

    errors: List[str] = []
    seen = set()
    for descriptor in descriptors:
        if descriptor.plugin_id in seen:
            errors.append(f"{descriptor.plugin_id}: duplicate plugin id")
        seen.add(descriptor.plugin_id)

    schema = _load_schema(SCHEMA_PATH)
    for descriptor in descriptors:
        payload = _descriptor_to_dict(descriptor)
        errors.extend(f"{descriptor.plugin_id}: {msg}" for msg in _validate(payload, schema))

    return errors


def resolve_enabled_critique_plugins(enabled: Optional[Sequence[str]]) -> List[CritiqueRulePlugin]:
    registry = {plugin.descriptor.plugin_id: plugin for plugin in _critique_plugins()}
    by_rule_id = {plugin.descriptor.plugin_id.split(".", 1)[-1]: plugin for plugin in registry.values()}

    if not enabled:
        return [registry[key] for key in sorted(registry.keys())]

    selected: List[CritiqueRulePlugin] = []
    for rule_id in enabled:
        plugin = registry.get(rule_id) or by_rule_id.get(rule_id)
        if not plugin:
            available = ", ".join(sorted(by_rule_id.keys()))
            raise ValueError(f"Unknown architecture rule '{rule_id}'. Available: {available}")
        selected.append(plugin)
    return selected


def get_repro_plugins() -> List[ReproCheckPlugin]:
    return _repro_plugins()


def _critique_plugins() -> List[CritiqueRulePlugin]:
    registry = get_rule_registry()
    plugins: List[CritiqueRulePlugin] = []
    for rule_id, rule in registry.items():
        descriptor = PluginDescriptor(
            plugin_id=f"critique_rule.{rule_id}",
            kind="critique_rule",
            name=rule_id,
            description=rule.description,
            version="1.0",
            entrypoint=f"paperfig.critique.rules:{rule_id}",
            enabled_by_default=True,
            tags=["architecture", "critique"],
        )
        plugins.append(CritiqueRulePlugin(descriptor=descriptor, evaluator=rule.evaluator))
    return plugins


def _repro_plugins() -> List[ReproCheckPlugin]:
    registry = get_repro_check_registry()
    plugins: List[ReproCheckPlugin] = []
    for check_id, check in registry.items():
        descriptor = PluginDescriptor(
            plugin_id=f"repro_check.{check_id}",
            kind="repro_check",
            name=check_id,
            description=check.description,
            version="1.0",
            entrypoint=f"paperfig.audits.repro_checks:{check_id}",
            enabled_by_default=True,
            tags=["repro", "audit"],
        )
        plugins.append(ReproCheckPlugin(descriptor=descriptor, evaluator=check.evaluator))
    return plugins


def _load_schema(path: Path) -> Dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"Plugin schema not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _simple_validate(data: Dict[str, object], schema: Dict[str, object]) -> List[str]:
    errors: List[str] = []
    for field in schema.get("required", []):
        if field not in data:
            errors.append(f"{field}: is required")
    return errors


def _validate(data: Dict[str, object], schema: Dict[str, object]) -> List[str]:
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


def _descriptor_to_dict(descriptor: PluginDescriptor) -> Dict[str, object]:
    return {
        "plugin_id": descriptor.plugin_id,
        "kind": descriptor.kind,
        "name": descriptor.name,
        "description": descriptor.description,
        "version": descriptor.version,
        "entrypoint": descriptor.entrypoint,
        "enabled_by_default": descriptor.enabled_by_default,
        "tags": descriptor.tags,
    }
