# paperfig
[![CI](https://github.com/oluwafemidiakhoa/paperfigg/actions/workflows/ci.yml/badge.svg)](https://github.com/oluwafemidiakhoa/paperfigg/actions/workflows/ci.yml)
[![Docs Drift](https://github.com/oluwafemidiakhoa/paperfigg/actions/workflows/docs-drift.yml/badge.svg)](https://github.com/oluwafemidiakhoa/paperfigg/actions/workflows/docs-drift.yml)
[![Publish](https://github.com/oluwafemidiakhoa/paperfigg/actions/workflows/publish.yml/badge.svg)](https://github.com/oluwafemidiakhoa/paperfigg/actions/workflows/publish.yml)

`paperfig` is a production-grade CLI that converts research papers (PDF or Markdown) into publication-ready academic figures using an agentic planning -> generation -> critique pipeline.

The core differentiator is that agent reasoning and architecture decisions are stored as versioned repo artifacts (architecture docs, flows, Mermaid diagrams, templates, audits) so humans and agents can evolve the system together.

## Install
> **Warning**
> `paperfig` on PyPI is a different project; install `paperfigg`. The CLI command remains `paperfig`.

- Standard CLI + PNG export:
  - `pip install "paperfigg[cli,png]"`
- Developer tooling:
  - `pip install "paperfigg[cli,png,dev,yaml,pdf,mcp]"`
- CLI-first local install:
  - `pipx install .`
  - `uv tool install .`
  - Published package name is `paperfigg`; CLI command remains `paperfig`.

## Quickstart (Mock Mode, No Keys)
Mock mode is designed for instant local runs and realistic output artifacts.

```bash
pip install "paperfigg[cli,png]"
paperfig doctor
paperfig generate examples/sample_paper.md --mode mock
paperfig docs check
```

## 1-Minute Demo
```bash
pip install "paperfigg[cli,png]"
paperfig doctor
paperfig generate examples/sample_paper.md --mode mock
ls runs/*/figures/*/final/figure.svg
```

## Full Mode (PaperBanana MCP)
Use full mode when you want real PaperBanana generation via MCP.

```bash
pip install "paperfigg[cli,png,mcp]"
export PAPERFIG_MCP_SERVER=paperbanana
export PAPERFIG_MCP_COMMAND="python -m your_mcp_server"
paperfig doctor --probe-mcp
paperfig generate examples/sample_paper.md --mode real
```

## What's New In v0.3.0
- Contributor flywheel:
  - `paperfig templates lint` validates flow templates against JSON Schema.
  - Domain-pack loading supports directory or Python package packs via `--pack` and `--template-pack`.
  - Architecture critique supports rule plugins with `--list-rules` and `--enable`.
- Deterministic reproducibility:
  - `paperfig rerun <run_id>` replays a run deterministically from saved artifacts.
  - `paperfig diff <run_id_1> <run_id_2>` compares run metrics and writes `diff.json`.
- Contributor mode:
  - `paperfig generate ... --contrib` writes planner notes, critic notes, `CONTRIBUTING_NOTES.md`, and `contrib.log`.
- Windows PNG enablement:
  - `paperfig doctor --fix png --verify` prints guided setup and verification steps.
  - PNG export warnings point to `paperfig doctor --fix png`.

## What You Get
- Generated figures (SVG and optional transparent PNG)
- LaTeX include snippets
- Captions and figure plans
- Traceability mapping from figure elements to source text spans
- Governance artifacts (`docs_drift_report.json`, `architecture_critique.json`, `repro_audit.json`)

Sample proof assets are committed in `docs/gallery/sample_paper`:
- `docs/gallery/sample_paper/fig-21a078a0.svg`
- `docs/gallery/sample_paper/plan.json`
- `docs/gallery/sample_paper/repro_audit.json`
- `docs/gallery/sample_paper/architecture_critique.json`

![Sample methodology figure](docs/gallery/sample_paper/fig-21a078a0.svg)

## What It Does
- Parses papers and extracts methodology, system description, and results sections.
- Plans figures through reusable flow templates and fallback heuristics.
- Generates figures via PaperBanana MCP and iterates with critique feedback loops.
- Regenerates docs and gates on drift for architecture governance.
- Runs reproducibility audits and architecture critiques as first-class run artifacts.
- Provides a constrained autonomous lab scaffold for iterative research experiments.

## How The Agentic System Works
The system uses specialized agents:
- `PlannerAgent` chooses figures and template-aligned abstractions.
- `GeneratorAgent` calls PaperBanana via MCP and emits traceable figure elements.
- `CriticAgent` scores faithfulness, readability, conciseness, and aesthetics.
- `ArchitectureCriticAgent` audits run-level architecture quality and governance completeness.

Full architecture documentation and flow diagrams live in `docs/architecture`.

## CLI Usage
<!-- AUTO-GEN:START cli-command-catalog -->
- `paperfig generate`
- `paperfig rerun`
- `paperfig diff`
- `paperfig critique`
- `paperfig export`
- `paperfig doctor`
- `paperfig inspect`
- `paperfig docs regenerate`
- `paperfig docs check`
- `paperfig templates list`
- `paperfig templates validate`
- `paperfig templates lint`
- `paperfig critique-architecture`
- `paperfig audit`
- `paperfig lab init`
- `paperfig lab propose`
- `paperfig lab run`
- `paperfig lab review`
- `paperfig lab status`
<!-- AUTO-GEN:END cli-command-catalog -->

## Flow Template Pack
<!-- AUTO-GEN:START flow-template-catalog -->
- `ablation_matrix` (ablation)
- `dataset_characteristics` (dataset_overview)
- `error_analysis_breakdown` (error_analysis)
- `limitations_threats_to_validity` (limitations)
- `methodology_pipeline` (methodology)
- `results_summary_plot` (results_plot)
- `system_overview` (system_overview)
- `training_compute_profile` (compute_profile)
<!-- AUTO-GEN:END flow-template-catalog -->

## Outputs
Each run creates a `runs/<run_id>/` workspace containing:
- `figures/<figure_id>/figure.svg`
- `figures/<figure_id>/traceability.json`
- `captions.txt`
- `inspect.json`
- `docs_drift_report.json`
- `architecture_critique.json`
- `repro_audit.json`
- `planner_notes.md`, `CONTRIBUTING_NOTES.md`, and `contrib.log` when `--contrib` is enabled
- `exports/` with PNG, SVG, LaTeX snippets, and `export_report.json`

## Configuration
Default config lives in `paperfig.yaml`:
- docs scope and manifest path (`docs/docs_manifest.yaml`)
- architecture critique mode and severity gate
- reproducibility audit mode (`soft` by default)
- template pack (`expanded_v1`)
- lab registry path and sandbox policy (`config/lab_policy.yaml`)

## Verification
- Run unit/integration tests: `python3 -m unittest discover -s tests -v`
- Run docs drift check: `./scripts/check_docs_drift.sh`
- Run full quality checks: `./scripts/check_quality.sh`

## CI
- GitHub Actions pipeline: `.github/workflows/ci.yml`
- GitHub Actions docs drift gate: `.github/workflows/docs-drift.yml`
- GitHub Actions PyPI publish: `.github/workflows/publish.yml`
- Publish workflow uses PyPI Trusted Publishing (OIDC) with GitHub environment `pypi`.
- Manual `publish.yml` runs are dry-run by default; set workflow input `publish=true` to actually upload.
- GitLab pipeline: `.gitlab-ci.yml`
- All wrappers call shared scripts in `scripts/` (no duplicated CI logic in YAML)

## Community
- Changelog: `CHANGELOG.md`
- Contributing: `CONTRIBUTING.md`
- Code of conduct: `CODE_OF_CONDUCT.md`
- Citation metadata: `CITATION.cff`

## Architecture Docs
See:
- `docs/architecture/AI-Architecture-Analysis.md`
- `docs/architecture/flows/index.md`
- `docs/templates/HOW_TO_ADD_A_FLOW.md`
- `docs/templates/DOMAIN_PACKS.md`
- `docs/platform/WINDOWS_PNG.md`

## Publish Troubleshooting
- Package name on PyPI is `paperfigg` (not `paperfig`).
- If publish fails with "file already exists", rerun is safe because publish uses `skip-existing: true`.
- If publish fails with OIDC/token project mismatch:
  - verify Trusted Publisher is configured for project `paperfigg`
  - owner/repo must be `oluwafemidiakhoa/paperfigg`
  - workflow must be `publish.yml`
  - environment name must be `pypi`
