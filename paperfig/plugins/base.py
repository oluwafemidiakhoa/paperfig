from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from paperfig.utils.types import ArchitectureCritiqueFinding, PluginDescriptor, ReproAuditCheck


@dataclass(frozen=True)
class PluginBase:
    descriptor: PluginDescriptor


CritiqueEvaluator = Callable[[object], Sequence[ArchitectureCritiqueFinding]]
ReproEvaluator = Callable[[object, str | None], ReproAuditCheck]


@dataclass(frozen=True)
class CritiqueRulePlugin(PluginBase):
    evaluator: CritiqueEvaluator


@dataclass(frozen=True)
class ReproCheckPlugin(PluginBase):
    evaluator: ReproEvaluator
