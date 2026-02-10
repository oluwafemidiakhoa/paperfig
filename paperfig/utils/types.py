from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class PaperSection:
    name: str
    text: str
    start: int
    end: int


@dataclass
class PaperContent:
    source_path: str
    full_text: str
    sections: Dict[str, PaperSection]


@dataclass
class FigurePlan:
    figure_id: str
    title: str
    kind: str
    order: int
    abstraction_level: str
    description: str
    justification: str
    template_id: str = ""
    source_spans: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FigureCandidate:
    figure_id: str
    svg_path: str
    element_metadata_path: str
    traceability_path: str


@dataclass
class CritiqueReport:
    figure_id: str
    score: float
    threshold: float
    quality_dimensions: Dict[str, float]
    dimension_threshold: float
    failed_dimensions: List[str]
    issues: List[str]
    recommendations: List[str]
    passed: bool


@dataclass
class ArchitectureCritiqueFinding:
    finding_id: str
    severity: str
    title: str
    description: str
    evidence: str
    suggestion: str


@dataclass
class ArchitectureCritiqueReport:
    run_id: str
    block_severity: str
    findings: List[ArchitectureCritiqueFinding] = field(default_factory=list)
    blocked: bool = False
    summary: str = ""
    generated_at: str = ""


@dataclass
class ReproAuditCheck:
    check_id: str
    description: str
    required: bool
    passed: bool
    severity: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReproAuditReport:
    run_id: str
    mode: str
    checks: List[ReproAuditCheck] = field(default_factory=list)
    passed: bool = True
    summary: str = ""
    generated_at: str = ""
    environment: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowTemplate:
    template_id: str
    title: str
    kind: str
    order_hint: int
    required_sections: List[str]
    trigger_rules: List[Dict[str, Any]]
    element_blueprint: Dict[str, Any]
    caption_style: str
    traceability_requirements: Dict[str, Any]
    critique_focus: List[str]
    name: str = ""
    template_type: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    steps: List[Dict[str, Any]] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)
    scoring: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowTemplateCatalog:
    pack_id: str
    templates: List[FlowTemplate] = field(default_factory=list)


@dataclass
class FigureContract:
    contract_id: str
    schema_version: str
    run_id: str
    figure_id: str
    title: str
    kind: str
    template_id: str
    order: int
    abstraction_level: str
    required_sections: List[str] = field(default_factory=list)
    source_spans: List[Dict[str, Any]] = field(default_factory=list)
    traceability_requirements: Dict[str, Any] = field(default_factory=dict)
    invariants: List[str] = field(default_factory=list)
    created_at: str = ""


@dataclass
class InspectHtmlManifest:
    run_id: str
    generated_at: str
    html_path: str
    artifacts: List[str] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginDescriptor:
    plugin_id: str
    kind: str
    name: str
    description: str
    version: str
    entrypoint: str
    enabled_by_default: bool = True
    tags: List[str] = field(default_factory=list)


@dataclass
class RegressionReport:
    report_id: str
    paper_v1: str
    paper_v2: str
    run_id_v1: str
    run_id_v2: str
    generated_at: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    invariants: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    diff_report: Optional[str] = None
    report_dir: str = ""


@dataclass
class JournalProfile:
    profile_id: str
    name: str
    version: str
    quality_threshold: float
    dimension_threshold: float
    max_iterations: int
    required_kinds: List[str] = field(default_factory=list)
    arch_critique_block_severity: str = "critical"
    repro_audit_mode: str = "soft"
    template_pack: str = "expanded_v1"
    notes: str = ""
