from __future__ import annotations

import importlib
import json
import os
import platform
from pathlib import Path
import shlex
import shutil
from typing import List, Optional

import typer

from paperfig import __version__

PACKAGE_NAME = "paperfigg"
from paperfig.agents.architecture_critic import SEVERITY_ORDER
from paperfig.agents.critic import CriticAgent
from paperfig.command_catalog import get_command_catalog
from paperfig.lab.orchestrator import LabOrchestrator
from paperfig.pipeline.orchestrator import Orchestrator
from paperfig.templates.lint import lint_template_catalog
from paperfig.templates.loader import load_template_catalog, validate_template_catalog
from paperfig.utils.config import load_config
from paperfig.utils.paperbanana import PaperBananaClient
from paperfig.utils.pdf_parser import parse_paper
from paperfig.utils.types import FigurePlan, PaperContent, PaperSection

app = typer.Typer(help="Generate publication-ready figures from research papers.")
docs_app = typer.Typer(help="Documentation regeneration and drift checks.")
templates_app = typer.Typer(help="Flow template utilities.")
lab_app = typer.Typer(help="Autonomous research lab workflows.")

app.add_typer(docs_app, name="docs")
app.add_typer(templates_app, name="templates")
app.add_typer(lab_app, name="lab")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show paperfig version and exit.",
    ),
) -> None:
    del version


def _lab_orchestrator() -> LabOrchestrator:
    config = load_config()
    lab_cfg = config.get("lab", {})
    return LabOrchestrator(
        root_dir=Path(str(lab_cfg.get("registry_dir", "lab_runs"))),
        policy_path=Path(str(lab_cfg.get("sandbox_policy", "config/lab_policy.yaml"))),
        runs_root=Path("runs"),
    )


def _dependency_check(module_name: str, required: bool) -> dict:
    try:
        importlib.import_module(module_name)
        return {
            "check": f"python_module:{module_name}",
            "status": "ok",
            "required": required,
            "message": f"Module '{module_name}' is importable.",
        }
    except Exception as exc:
        status = "fail" if required else "warn"
        message = f"Module '{module_name}' is unavailable: {exc}"
        if module_name == "cairosvg":
            message = f"{message} Run: paperfig doctor --fix png"
        return {
            "check": f"python_module:{module_name}",
            "status": status,
            "required": required,
            "message": message,
        }


def _png_fix_guidance() -> str:
    system = platform.system().lower()
    if system.startswith("windows"):
        return "\n".join(
            [
                "Windows PNG setup options:",
                "1) MSYS2 UCRT64 (recommended for system-wide Cairo):",
                "   - winget install MSYS2.MSYS2",
                "   - C:\\msys64\\ucrt64.exe",
                "   - pacman -Syu",
                "   - pacman -S --needed mingw-w64-ucrt-x86_64-cairo mingw-w64-ucrt-x86_64-pango mingw-w64-ucrt-x86_64-gdk-pixbuf2",
                "   - Add C:\\msys64\\ucrt64\\bin to PATH",
                "2) Conda-forge environment:",
                "   - conda create -n paperfig-png python=3.10 cairosvg cairo pango gdk-pixbuf -c conda-forge",
                "   - conda activate paperfig-png",
                "Verification:",
                "   - paperfig doctor --fix png --verify",
                "   - paperfig doctor",
            ]
        )
    return "\n".join(
        [
            "Install Cairo system libraries and cairosvg for PNG export.",
            "Then verify with:",
            "  - paperfig doctor --fix png --verify",
            "  - paperfig doctor",
        ]
    )


def _mcp_check(probe_mcp: bool) -> dict:
    if os.getenv("PAPERFIG_MOCK_PAPERBANANA", "0") == "1":
        return {
            "check": "paperbanana_mcp",
            "status": "ok",
            "required": False,
            "message": "Mock mode is enabled (PAPERFIG_MOCK_PAPERBANANA=1); real MCP probe skipped.",
        }

    server = os.getenv("PAPERFIG_MCP_SERVER", "").strip()
    factory = os.getenv("PAPERFIG_MCP_CLIENT_FACTORY", "").strip()
    command = os.getenv("PAPERFIG_MCP_COMMAND", "").strip()

    if not server:
        return {
            "check": "paperbanana_mcp",
            "status": "warn",
            "required": False,
            "message": "PAPERFIG_MCP_SERVER is not configured.",
        }

    if not factory and not command:
        return {
            "check": "paperbanana_mcp",
            "status": "warn",
            "required": False,
            "message": "No MCP transport configured. Set PAPERFIG_MCP_CLIENT_FACTORY or PAPERFIG_MCP_COMMAND.",
        }

    if command:
        command_parts = shlex.split(command)
        command_bin = command_parts[0] if command_parts else ""
        if not command_bin:
            return {
                "check": "paperbanana_mcp",
                "status": "fail",
                "required": False,
                "message": "PAPERFIG_MCP_COMMAND is set but empty after parsing.",
            }
        if shutil.which(command_bin) is None:
            return {
                "check": "paperbanana_mcp",
                "status": "fail",
                "required": False,
                "message": f"MCP command binary '{command_bin}' is not on PATH.",
            }

    if not probe_mcp:
        return {
            "check": "paperbanana_mcp",
            "status": "ok",
            "required": False,
            "message": "MCP configuration detected. Run `paperfig doctor --probe-mcp` for an end-to-end probe.",
        }

    try:
        client = PaperBananaClient()
        client.generate_svg(
            {
                "figure_id": "doctor-probe",
                "title": "doctor-probe",
                "kind": "system_overview",
                "description": "Connectivity probe",
                "abstraction_level": "high",
                "source_text": {"methodology": "", "system": "", "results": ""},
                "source_spans": [],
                "style_refs": {},
                "critique_feedback": {},
                "iteration": 1,
            }
        )
        return {
            "check": "paperbanana_mcp",
            "status": "ok",
            "required": False,
            "message": "MCP probe succeeded via `paperbanana.generate`.",
        }
    except Exception as exc:
        return {
            "check": "paperbanana_mcp",
            "status": "fail",
            "required": False,
            "message": f"MCP probe failed: {exc}",
        }


def _render_doctor_output(report: dict) -> None:
    checks = report.get("checks", [])
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title="paperfig doctor")
        table.add_column("Check", justify="left")
        table.add_column("Status", justify="left")
        table.add_column("Required", justify="center")
        table.add_column("Message", justify="left")

        status_style = {"ok": "green", "warn": "yellow", "fail": "red"}
        for check in checks:
            status = str(check.get("status", "warn"))
            table.add_row(
                str(check.get("check", "")),
                f"[{status_style.get(status, 'white')}]{status}[/{status_style.get(status, 'white')}]",
                "yes" if check.get("required", False) else "no",
                str(check.get("message", "")),
            )

        console = Console()
        console.print(table)
        console.print(f"Package: {PACKAGE_NAME} | Command: paperfig")
        console.print(
            f"Overall: {'PASS' if report.get('passed') else 'FAIL'} "
            f"(required failures: {report.get('required_failures', 0)}, "
            f"optional failures: {report.get('optional_failures', 0)})"
        )
    except Exception:
        typer.echo("paperfig doctor")
        for check in checks:
            typer.echo(
                f"- {check.get('check')}: {check.get('status')} "
                f"(required={check.get('required')}) {check.get('message')}"
            )
        typer.echo(f"Package: {PACKAGE_NAME} | Command: paperfig")
        typer.echo(
            "Overall: "
            f"{'PASS' if report.get('passed') else 'FAIL'} "
            f"(required failures: {report.get('required_failures', 0)}, "
            f"optional failures: {report.get('optional_failures', 0)})"
        )


@app.command()
def generate(
    paper_path: Path = typer.Argument(..., exists=True, help="Path to paper PDF or Markdown"),
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="PaperBanana execution mode: auto, mock, or real.",
    ),
    run_root: Path = typer.Option(Path("runs"), help="Root directory for run outputs"),
    max_iterations: int = typer.Option(3, help="Maximum generation iterations per figure"),
    quality_threshold: float = typer.Option(0.75, help="Minimum critique score to accept a figure"),
    dimension_threshold: float = typer.Option(
        0.55,
        help="Minimum score required for each critique dimension.",
    ),
    template_pack: Optional[str] = typer.Option(
        None,
        help="Template pack ID for planner flow templates.",
    ),
    arch_critique_mode: str = typer.Option(
        "inline",
        help="Architecture critique mode: inline or off.",
    ),
    arch_critique_block_severity: str = typer.Option(
        "critical",
        help="Minimum architecture finding severity that blocks generation.",
    ),
    repro_audit_mode: str = typer.Option(
        "soft",
        help="Reproducibility audit mode: soft or hard.",
    ),
    contrib: bool = typer.Option(
        False,
        "--contrib",
        help="Contributor mode: verbose artifacts, planner/critic notes, and run CONTRIBUTING_NOTES.",
    ),
) -> None:
    if mode not in {"auto", "mock", "real"}:
        raise typer.BadParameter("mode must be one of: auto, mock, real")
    if arch_critique_mode not in {"inline", "off"}:
        raise typer.BadParameter("arch_critique_mode must be one of: inline, off")
    if arch_critique_block_severity not in SEVERITY_ORDER:
        raise typer.BadParameter(
            f"arch_critique_block_severity must be one of: {', '.join(SEVERITY_ORDER.keys())}"
        )
    if repro_audit_mode not in {"soft", "hard"}:
        raise typer.BadParameter("repro_audit_mode must be one of: soft, hard")

    previous_mock_mode = os.getenv("PAPERFIG_MOCK_PAPERBANANA")
    if mode == "mock":
        os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "1"
    elif mode == "real":
        os.environ["PAPERFIG_MOCK_PAPERBANANA"] = "0"

    try:
        orchestrator = Orchestrator(
            run_root=run_root,
            max_iterations=max_iterations,
            quality_threshold=quality_threshold,
            dimension_threshold=dimension_threshold,
            template_pack=template_pack,
            arch_critique_mode=arch_critique_mode,
            arch_critique_block_severity=arch_critique_block_severity,
            repro_audit_mode=repro_audit_mode,
        )
        run_id = orchestrator.generate(paper_path, contrib=contrib)
    except RuntimeError as exc:
        typer.echo(f"Generation failed: {exc}")
        raise typer.Exit(code=1)
    finally:
        if mode in {"mock", "real"}:
            if previous_mock_mode is None:
                os.environ.pop("PAPERFIG_MOCK_PAPERBANANA", None)
            else:
                os.environ["PAPERFIG_MOCK_PAPERBANANA"] = previous_mock_mode

    typer.echo(f"Run created: {run_id}")
    typer.echo(f"Output directory: {run_root / run_id}")


@app.command()
def critique(
    figure_path: Path = typer.Argument(..., exists=True, help="Path to figure SVG"),
    paper_path: Optional[Path] = typer.Option(None, help="Optional paper PDF or Markdown for context"),
    threshold: float = typer.Option(0.75, help="Critique acceptance threshold"),
    dimension_threshold: float = typer.Option(
        0.55,
        help="Minimum score required for each critique dimension.",
    ),
) -> None:
    if paper_path:
        paper = parse_paper(paper_path)
    else:
        paper = PaperContent(
            source_path="",
            full_text="",
            sections={
                "methodology": PaperSection("methodology", "", 0, 0),
                "system": PaperSection("system", "", 0, 0),
                "results": PaperSection("results", "", 0, 0),
            },
        )

    plan = FigurePlan(
        figure_id=figure_path.stem,
        title=figure_path.stem,
        kind="ad_hoc",
        order=1,
        abstraction_level="unknown",
        description="Ad-hoc critique",
        justification="Manual critique invocation",
        template_id="manual",
        source_spans=[],
    )

    critic = CriticAgent(threshold=threshold, dimension_threshold=dimension_threshold)
    report = critic.critique(figure_path, plan, paper)
    typer.echo(json.dumps(report.__dict__, indent=2))


@app.command()
def rerun(
    run_id: str = typer.Argument(..., help="Existing run ID to replay deterministically"),
    run_root: Path = typer.Option(Path("runs"), help="Root directory for run outputs"),
    contrib: bool = typer.Option(
        False,
        "--contrib",
        help="Contributor mode for the replayed run.",
    ),
) -> None:
    orchestrator = Orchestrator(run_root=run_root)
    try:
        new_run_id = orchestrator.rerun(source_run_id=run_id, contrib=contrib)
    except RuntimeError as exc:
        typer.echo(f"Rerun failed: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Rerun created: {new_run_id}")
    typer.echo(f"Output directory: {run_root / new_run_id}")


@app.command()
def diff(
    run_id_1: str = typer.Argument(..., help="Base run ID"),
    run_id_2: str = typer.Argument(..., help="Target run ID"),
    run_root: Path = typer.Option(Path("runs"), help="Root directory for run outputs"),
    output_dir: Optional[Path] = typer.Option(None, help="Optional output directory for diff artifacts"),
    as_json: bool = typer.Option(False, "--as-json", help="Print diff report as JSON"),
) -> None:
    orchestrator = Orchestrator(run_root=run_root)
    report = orchestrator.diff(run_id_1=run_id_1, run_id_2=run_id_2, output_dir=output_dir)
    if as_json:
        typer.echo(json.dumps(report, indent=2))
        return

    typer.echo(f"Run 1: {run_id_1}")
    typer.echo(f"Run 2: {run_id_2}")
    typer.echo(f"Diff output: {Path(report.get('diff_dir', '')) / 'diff.json'}")
    metrics = report.get("metrics", {})
    typer.echo(
        "accepted_count: "
        f"{metrics.get('accepted_count', {}).get('run_1')} -> "
        f"{metrics.get('accepted_count', {}).get('run_2')}"
    )
    typer.echo(
        "avg_final_score: "
        f"{metrics.get('avg_final_score', {}).get('run_1')} -> "
        f"{metrics.get('avg_final_score', {}).get('run_2')}"
    )
    typer.echo(
        "avg_traceability_coverage: "
        f"{metrics.get('avg_traceability_coverage', {}).get('run_1')} -> "
        f"{metrics.get('avg_traceability_coverage', {}).get('run_2')}"
    )
    typer.echo(f"Changed figures: {len(report.get('changed_figures', []))}")
    typer.echo(f"Changed JSON artifacts: {len(report.get('changed_artifacts', []))}")


@app.command()
def export(
    run_id: str = typer.Argument(..., help="Run ID to export"),
    run_root: Path = typer.Option(Path("runs"), help="Root directory for run outputs"),
    output_dir: Optional[Path] = typer.Option(None, help="Optional export output directory"),
) -> None:
    orchestrator = Orchestrator(run_root=run_root)
    export_root = orchestrator.export(run_id, output_dir=output_dir)
    typer.echo(f"Exports written to: {export_root}")
    report_path = export_root / "export_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        for warning in report.get("warnings", []):
            typer.echo(f"Warning: {warning}")


@app.command()
def doctor(
    as_json: bool = typer.Option(False, "--as-json", help="Print doctor report as JSON."),
    probe_mcp: bool = typer.Option(
        False,
        "--probe-mcp",
        help="Attempt an end-to-end PaperBanana MCP probe.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Exit non-zero if any check reports failure.",
    ),
    fix: Optional[str] = typer.Option(
        None,
        "--fix",
        help="Show guided fix instructions for a subsystem (currently: png).",
    ),
    verify: bool = typer.Option(
        False,
        "--verify",
        help="Re-run targeted verification for the selected --fix subsystem.",
    ),
) -> None:
    if fix and fix not in {"png"}:
        raise typer.BadParameter("fix must be one of: png")

    checks = [
        _dependency_check("typer", required=True),
        _dependency_check("rich", required=False),
        _dependency_check("cairosvg", required=False),
        _mcp_check(probe_mcp=probe_mcp),
    ]

    required_failures = sum(
        1 for check in checks if check.get("required", False) and check.get("status") == "fail"
    )
    optional_failures = sum(
        1 for check in checks if not check.get("required", False) and check.get("status") == "fail"
    )

    report = {
        "version": __version__,
        "checks": checks,
        "probe_mcp": probe_mcp,
        "required_failures": required_failures,
        "optional_failures": optional_failures,
        "passed": required_failures == 0,
    }

    if as_json:
        typer.echo(json.dumps(report, indent=2))
    else:
        _render_doctor_output(report)
        if fix == "png":
            typer.echo("")
            typer.echo(_png_fix_guidance())
            if verify:
                verify_check = _dependency_check("cairosvg", required=False)
                typer.echo("")
                typer.echo(
                    "PNG verify: "
                    f"{verify_check.get('status')} - {verify_check.get('message')}"
                )

    if required_failures > 0:
        raise typer.Exit(code=1)
    if strict and optional_failures > 0:
        raise typer.Exit(code=1)


@app.command(name="critique-architecture")
def critique_architecture(
    run_id: Optional[str] = typer.Argument(None, help="Run ID to critique"),
    run_root: Path = typer.Option(Path("runs"), help="Root directory for run outputs"),
    as_json: bool = typer.Option(False, "--as-json", help="Print report as JSON"),
    block_severity: str = typer.Option(
        "critical",
        help="Severity threshold that marks the report as blocking.",
    ),
    list_rules: bool = typer.Option(False, "--list-rules", help="List built-in architecture rules and exit."),
    enable: Optional[List[str]] = typer.Option(
        None,
        "--enable",
        help="Enable a subset of architecture rules (repeatable). Default: all built-in rules.",
    ),
) -> None:
    if block_severity not in SEVERITY_ORDER:
        raise typer.BadParameter(
            f"block_severity must be one of: {', '.join(SEVERITY_ORDER.keys())}"
        )

    orchestrator = Orchestrator(run_root=run_root)
    if list_rules:
        for rule in orchestrator.architecture_critic.available_rules():
            typer.echo(f"- {rule['rule_id']}: {rule['description']}")
        return
    if not run_id:
        raise typer.BadParameter("run_id is required unless --list-rules is provided")

    try:
        report = orchestrator.critique_architecture(
            run_id=run_id,
            block_severity=block_severity,
            persist=True,
            enabled_rules=enable,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if as_json:
        typer.echo(json.dumps(report, indent=2))
        return

    typer.echo(f"Run: {run_id}")
    typer.echo(f"Summary: {report.get('summary')}")
    typer.echo(f"Blocked: {report.get('blocked')}")
    findings = report.get("findings", [])
    for finding in findings:
        typer.echo(f"- [{finding.get('severity')}] {finding.get('title')}: {finding.get('description')}")


@app.command()
def audit(
    run_id: str = typer.Argument(..., help="Run ID to audit"),
    run_root: Path = typer.Option(Path("runs"), help="Root directory for run outputs"),
    mode: str = typer.Option("soft", help="Audit mode: soft or hard"),
    as_json: bool = typer.Option(False, "--as-json", help="Print report as JSON"),
) -> None:
    if mode not in {"soft", "hard"}:
        raise typer.BadParameter("mode must be one of: soft, hard")

    orchestrator = Orchestrator(run_root=run_root)
    report = orchestrator.audit(run_id=run_id, mode=mode, persist=True)

    if as_json:
        typer.echo(json.dumps(report, indent=2))
    else:
        typer.echo(f"Run: {run_id}")
        typer.echo(f"Mode: {mode}")
        typer.echo(f"Passed: {report.get('passed')}")
        typer.echo(f"Summary: {report.get('summary')}")

    if mode == "hard" and not report.get("passed", False):
        raise typer.Exit(code=1)


@app.command()
def inspect(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    run_root: Path = typer.Option(Path("runs"), help="Root directory for run outputs"),
    as_json: bool = typer.Option(False, "--as-json", help="Print the full summary JSON"),
    failures_only: bool = typer.Option(
        False,
        "--failures-only",
        help="Only include figures that did not pass final critique.",
    ),
    figure_id: Optional[str] = typer.Option(
        None,
        "--figure-id",
        help="Only include a specific figure ID.",
    ),
    min_score: Optional[float] = typer.Option(
        None,
        "--min-score",
        help="Only include figures with final score >= this value.",
    ),
    failed_dimension: Optional[str] = typer.Option(
        None,
        "--failed-dimension",
        help="Only include figures that failed a specific dimension.",
    ),
    output_path: Optional[Path] = typer.Option(None, help="Optional path to write summary JSON"),
) -> None:
    orchestrator = Orchestrator(run_root=run_root)
    summary = orchestrator.inspect(
        run_id,
        failures_only=failures_only,
        figure_id=figure_id,
        min_score=min_score,
        failed_dimension=failed_dimension,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        typer.echo(f"Summary written to: {output_path}")

    if as_json:
        typer.echo(json.dumps(summary, indent=2))
        return

    aggregate = summary.get("aggregate", {})
    metadata = summary.get("metadata", {})
    typer.echo(f"Run: {summary.get('run_id')}")
    if metadata.get("paper_path"):
        typer.echo(f"Paper: {metadata['paper_path']}")
    typer.echo(
        "Figures: "
        f"{aggregate.get('accepted_count', 0)}/{aggregate.get('total_figures', 0)} accepted, "
        f"{aggregate.get('failed_count', 0)} failed"
    )
    typer.echo(
        "Averages: "
        f"score={aggregate.get('avg_final_score')} "
        f"traceability_coverage={aggregate.get('avg_traceability_coverage')}"
    )

    for figure in summary.get("figures", []):
        coverage = figure.get("traceability", {}).get("coverage")
        coverage_text = f"{coverage:.2f}" if isinstance(coverage, (int, float)) else "n/a"
        typer.echo(
            f"- {figure.get('figure_id')} "
            f"passed={figure.get('final_passed')} "
            f"iter={figure.get('iterations_attempted')} "
            f"score={figure.get('final_score')} "
            f"coverage={coverage_text}"
        )
        issues = figure.get("issues") or []
        if issues:
            typer.echo(f"  issue: {issues[0]}")

    for warning in summary.get("warnings", []):
        typer.echo(f"Warning: {warning}")


@docs_app.command("regenerate")
def docs_regenerate(
    check: bool = typer.Option(False, "--check", help="Check for drift without applying changes."),
    report_path: Optional[Path] = typer.Option(None, help="Optional path to write drift report JSON."),
) -> None:
    orchestrator = Orchestrator()
    report = orchestrator.docs_regenerate(check_only=check, report_path=report_path)

    typer.echo(f"Checked documents: {len(report.get('documents', []))}")
    typer.echo(f"Drift detected: {report.get('drift_detected')}")

    if check and report.get("drift_detected"):
        raise typer.Exit(code=1)


@docs_app.command("check")
def docs_check(
    report_path: Optional[Path] = typer.Option(None, help="Optional path to write drift report JSON."),
) -> None:
    docs_regenerate(check=True, report_path=report_path)


@templates_app.command("list")
def templates_list(
    template_dir: Path = typer.Option(Path("paperfig/templates/flows"), help="Template directory."),
    pack_id: str = typer.Option("expanded_v1", help="Template pack identifier."),
    pack: Optional[str] = typer.Option(
        None,
        "--pack",
        help="External template pack source (directory path or python package).",
    ),
) -> None:
    catalog = load_template_catalog(template_dir=template_dir, pack_id=pack_id, pack=pack)
    typer.echo(f"Template pack: {catalog.pack_id}")
    for template in catalog.templates:
        typer.echo(f"- {template.template_id}: {template.title} ({template.kind})")


@templates_app.command("validate")
def templates_validate(
    template_dir: Path = typer.Option(Path("paperfig/templates/flows"), help="Template directory."),
    pack_id: str = typer.Option("expanded_v1", help="Template pack identifier."),
    pack: Optional[str] = typer.Option(
        None,
        "--pack",
        help="External template pack source (directory path or python package).",
    ),
) -> None:
    errors = validate_template_catalog(template_dir=template_dir, pack_id=pack_id, pack=pack)
    if errors:
        for error in errors:
            typer.echo(f"Error: {error}")
        raise typer.Exit(code=1)
    typer.echo("Template catalog is valid.")


@templates_app.command("lint")
def templates_lint(
    template_dir: Path = typer.Option(Path("paperfig/templates/flows"), help="Template directory."),
    pack: Optional[str] = typer.Option(
        None,
        "--pack",
        help="External template pack source (directory path or python package).",
    ),
) -> None:
    errors = lint_template_catalog(template_dir=template_dir, pack=pack)
    if errors:
        for error in errors:
            typer.echo(f"Error: {error}")
        raise typer.Exit(code=1)
    typer.echo("Flow templates satisfy flow_template.schema.json.")


@lab_app.command("init")
def lab_init() -> None:
    orchestrator = _lab_orchestrator()
    lab_run_id = orchestrator.init_lab()
    typer.echo(f"Initialized lab run: {lab_run_id}")


@lab_app.command("propose")
def lab_propose(topic_or_run_id: str = typer.Argument(..., help="Topic text or existing run ID")) -> None:
    orchestrator = _lab_orchestrator()
    spec = orchestrator.propose(topic_or_run_id)
    typer.echo(f"Proposed experiment: {spec.experiment_id}")
    typer.echo(f"Command: {spec.command}")


@lab_app.command("run")
def lab_run(experiment_id: str = typer.Argument(..., help="Experiment ID")) -> None:
    orchestrator = _lab_orchestrator()
    result = orchestrator.run(experiment_id)
    typer.echo(f"Experiment: {experiment_id}")
    typer.echo(f"Status: {result.status}")
    typer.echo(f"Return code: {result.return_code}")
    if result.policy_violation:
        typer.echo(f"Policy violation: {result.policy_violation}")


@lab_app.command("review")
def lab_review(experiment_id: str = typer.Argument(..., help="Experiment ID")) -> None:
    orchestrator = _lab_orchestrator()
    review = orchestrator.review(experiment_id)
    typer.echo(f"Experiment: {experiment_id}")
    typer.echo(f"Recommendation: {review.get('recommendation')}")
    typer.echo(f"Rationale: {review.get('rationale')}")


@lab_app.command("status")
def lab_status(
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Optional lab run ID"),
) -> None:
    orchestrator = _lab_orchestrator()
    status = orchestrator.status(lab_run_id=run_id)
    typer.echo(f"Lab run: {status.get('lab_run_id')}")
    typer.echo(json.dumps(status.get("counts", {}), indent=2))
    for item in status.get("experiments", []):
        typer.echo(f"- {item.get('experiment_id')} status={item.get('status')} topic={item.get('topic')}")


@app.command("command-catalog")
def command_catalog() -> None:
    for command in get_command_catalog():
        typer.echo(command)


if __name__ == "__main__":
    app()
