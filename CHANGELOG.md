# Changelog

All notable changes to this project are documented in this file.

## [0.4.0] - 2026-02-10
- Added figure contracts (`contract.json`) with schema validation during critique and export.
- Added a self-contained HTML inspector via `paperfig inspect --html` with run-level manifests.
- Introduced a plugin registry for critique rules and reproducibility checks plus CLI utilities.
- Added paper regression detection with `paperfig regress` and persisted `regression_report.json`.
- Added journal mode (`--mode journal:neurips`) with stricter gates and required figure kinds.

## [0.3.0] - 2026-02-09
- Added a contributor flow-template framework with JSON Schema validation and `paperfig templates lint`.
- Added template-pack discovery from directory paths or Python package resources, including `paperfig templates list --pack`.
- Refactored architecture critique into plugin rules under `paperfig/critique/rules` with CLI rule controls (`--list-rules`, `--enable`).
- Added deterministic replay and comparison commands: `paperfig rerun` and `paperfig diff` with persisted `diff.json` artifacts.
- Added contributor mode (`paperfig generate --contrib`) to persist planner/critic notes and run-level `CONTRIBUTING_NOTES.md`.
- Added guided PNG remediation with `paperfig doctor --fix png` and improved PNG export warnings that include fix commands.
- Added contributor/platform docs for flow authoring, domain packs, and Windows PNG setup.

## [0.2.6] - 2026-02-08
- Fixed publish workflow compatibility on Python 3.10 by removing `tomllib` dependency in version verification.
- Fixed quality script execution chain to invoke docs drift checks via `bash`.

## [0.2.2] - 2026-02-08
- Fixed GitHub Actions script invocation by running shell scripts through `bash` in CI, docs-drift, and publish workflows.
- Added release hygiene to keep workflow and tag behavior consistent for PyPI publishing.

## [0.2.0] - 2026-02-08
- Added architecture governance with docs regeneration and drift gates.
- Added reusable YAML flow templates with expanded built-in figure pack.
- Added architecture critique agent and reproducibility audit artifacts.
- Added autonomous lab scaffold for propose/run/review/status workflows.
- Added `paperfig doctor` and `paperfig --version`.
- Added install extras (`cli`, `png`, `dev`) and proof gallery artifacts.
- Added GitHub Actions wrappers for quality and docs-drift scripts.
