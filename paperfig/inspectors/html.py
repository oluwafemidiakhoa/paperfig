from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List

from paperfig.contracts import load_contract, validate_contract_data
from paperfig.utils.types import InspectHtmlManifest


HTML_TITLE = "paperfig inspector"


def build_html_inspector(run_dir: Path, run_root: Path) -> InspectHtmlManifest:
    run_id = run_dir.name
    inspect_data = _read_json(run_dir / "inspect.json")
    architecture = _read_json(run_dir / "architecture_critique.json")
    repro = _read_json(run_dir / "repro_audit.json")
    docs_drift = _read_json(run_dir / "docs_drift_report.json")

    figures = _collect_figures(run_dir)
    diffs = _collect_diffs(run_root, run_id)

    payload = {
        "run_id": run_id,
        "inspect": inspect_data,
        "architecture_critique": architecture,
        "repro_audit": repro,
        "docs_drift": docs_drift,
        "figures": figures,
        "diffs": diffs,
    }

    inspect_dir = run_dir / "inspect"
    inspect_dir.mkdir(parents=True, exist_ok=True)
    html_path = inspect_dir / "index.html"
    html_path.write_text(_render_html(payload), encoding="utf-8")

    manifest = InspectHtmlManifest(
        run_id=run_id,
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        html_path=str(html_path),
        artifacts=[
            "inspect/index.html",
            "inspect/manifest.json",
            "inspect.json",
            "architecture_critique.json",
            "repro_audit.json",
            "docs_drift_report.json",
            "figures/*/final/figure.svg",
            "figures/*/contract.json",
        ],
        summary={
            "figure_count": len(figures),
            "diff_count": len(diffs),
        },
    )
    manifest_path = inspect_dir / "manifest.json"
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")
    return manifest


def _collect_figures(run_dir: Path) -> List[Dict[str, Any]]:
    figures: List[Dict[str, Any]] = []
    figures_dir = run_dir / "figures"
    if not figures_dir.exists():
        return figures

    for figure_dir in sorted([path for path in figures_dir.iterdir() if path.is_dir()]):
        final_dir = figure_dir / "final"
        svg_path = final_dir / "figure.svg"
        traceability_path = final_dir / "traceability.json"
        contract_path = figure_dir / "contract.json"

        svg_text = svg_path.read_text(encoding="utf-8") if svg_path.exists() else None
        traceability = _read_json(traceability_path)
        contract = load_contract(contract_path) if contract_path.exists() else None
        contract_errors: List[str] = []
        if isinstance(contract, dict):
            contract_errors = validate_contract_data(contract)

        critique = _latest_critique(figure_dir)

        figures.append(
            {
                "figure_id": figure_dir.name,
                "svg": svg_text,
                "traceability": traceability,
                "contract": contract,
                "contract_errors": contract_errors,
                "critique": critique,
                "final_svg_path": str(svg_path) if svg_path.exists() else None,
            }
        )

    return figures


def _latest_critique(figure_dir: Path) -> Dict[str, Any] | None:
    iter_dirs = sorted(
        [path for path in figure_dir.glob("iter_*") if path.is_dir()],
        key=lambda p: int(p.name.split("_")[1]) if "_" in p.name and p.name.split("_")[1].isdigit() else 0,
    )
    for iter_dir in reversed(iter_dirs):
        critique_path = iter_dir / "critique.json"
        if critique_path.exists():
            return _read_json(critique_path)
    return None


def _collect_diffs(run_root: Path, run_id: str) -> List[Dict[str, Any]]:
    diffs_root = run_root / "diffs"
    if not diffs_root.exists():
        return []
    reports: List[Dict[str, Any]] = []
    for diff_path in diffs_root.glob("**/diff.json"):
        data = _read_json(diff_path)
        if not isinstance(data, dict):
            continue
        if run_id in {data.get("run_id_1"), data.get("run_id_2")}:
            data = dict(data)
            data["diff_path"] = str(diff_path)
            reports.append(data)
    return reports


def _read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _render_html(payload: Dict[str, Any]) -> str:
    data_json = json.dumps(payload, indent=2).replace("</", "<\\/")

    template = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>__TITLE__</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial; margin: 24px; color: #1f2933; }
    h1 { font-size: 24px; margin-bottom: 8px; }
    h2 { font-size: 18px; margin-top: 24px; }
    .meta { color: #52606d; margin-bottom: 16px; }
    .card { border: 1px solid #e0e4e8; border-radius: 8px; padding: 16px; margin-bottom: 16px; background: #fafbfc; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; }
    .svg-box { border: 1px dashed #9fb3c8; padding: 8px; background: #fff; overflow: auto; }
    pre { white-space: pre-wrap; background: #f5f7fa; padding: 12px; border-radius: 6px; }
    .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; background: #d9e2ec; margin-right: 6px; }
    .warn { background: #ffe3c5; }
    .ok { background: #c6f6d5; }
  </style>
</head>
<body>
  <h1>__TITLE__</h1>
  <div class="meta">Run: <span id="run-id"></span></div>

  <div class="card">
    <h2>Summary</h2>
    <div id="summary"></div>
  </div>

  <div class="card">
    <h2>Architecture Critique</h2>
    <pre id="architecture"></pre>
  </div>

  <div class="card">
    <h2>Reproducibility Audit</h2>
    <pre id="repro"></pre>
  </div>

  <div class="card">
    <h2>Docs Drift Report</h2>
    <pre id="docs-drift"></pre>
  </div>

  <div class="card">
    <h2>Figures</h2>
    <div id="figures" class="grid"></div>
  </div>

  <div class="card">
    <h2>Diff Reports</h2>
    <pre id="diffs"></pre>
  </div>

  <script id="inspect-data" type="application/json">__DATA__</script>
  <script>
    const data = JSON.parse(document.getElementById('inspect-data').textContent);
    document.getElementById('run-id').textContent = data.run_id || 'unknown';

    const inspect = data.inspect || {};
    const aggregate = (inspect.aggregate || {});
    document.getElementById('summary').innerHTML = `
      <div class="badge">Figures: ${aggregate.accepted_count || 0}/${aggregate.total_figures || 0} accepted</div>
      <div class="badge">Avg score: ${aggregate.avg_final_score ?? 'n/a'}</div>
      <div class="badge">Avg traceability: ${aggregate.avg_traceability_coverage ?? 'n/a'}</div>
    `;

    document.getElementById('architecture').textContent = JSON.stringify(data.architecture_critique || {}, null, 2);
    document.getElementById('repro').textContent = JSON.stringify(data.repro_audit || {}, null, 2);
    document.getElementById('docs-drift').textContent = JSON.stringify(data.docs_drift || {}, null, 2);
    document.getElementById('diffs').textContent = JSON.stringify(data.diffs || [], null, 2);

    const figuresEl = document.getElementById('figures');
    (data.figures || []).forEach(fig => {
      const card = document.createElement('div');
      card.className = 'card';
      const contractErrors = fig.contract_errors || [];
      const contractBadge = contractErrors.length ? '<span class="badge warn">contract issues</span>' : '<span class="badge ok">contract ok</span>';
      card.innerHTML = `
        <h3>${fig.figure_id}</h3>
        ${contractBadge}
        <div class="svg-box">${fig.svg || '<em>SVG not found</em>'}</div>
        <h4>Critique</h4>
        <pre>${JSON.stringify(fig.critique || {}, null, 2)}</pre>
        <h4>Traceability</h4>
        <pre>${JSON.stringify(fig.traceability || {}, null, 2)}</pre>
        <h4>Contract</h4>
        <pre>${JSON.stringify(fig.contract || {}, null, 2)}</pre>
      `;
      figuresEl.appendChild(card);
    });
  </script>
</body>
</html>
"""

    return template.replace("__TITLE__", HTML_TITLE).replace("__DATA__", data_json)
