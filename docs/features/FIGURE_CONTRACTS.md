# Figure Contracts

## Overview
Figure contracts are machine-readable expectations for each generated figure. Every figure writes a
`contract.json` that captures its identity, expected sections, traceability requirements, and invariants.

## Artifacts
Each run writes:
- `figures/<figure_id>/contract.json`
- `figures/<figure_id>/final/contract.json`

The schema lives in `docs/schemas/figure_contract.schema.json`.

## Validation
Contracts are validated during critique and export. Contract violations:
- add critique issues and block acceptance
- add warnings to `export_report.json`

To audit contracts manually, open the JSON and confirm required fields are present and consistent
with `plan.json` and the template metadata.
