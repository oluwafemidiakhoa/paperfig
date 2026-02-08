# Changelog

All notable changes to this project are documented in this file.

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
