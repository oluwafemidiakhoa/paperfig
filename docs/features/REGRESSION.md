# Paper Regression Detection

## Usage
Compare two paper versions and produce a regression report:

```bash
paperfig regress paper_v1.md paper_v2.md
```

## Report
The command creates a report under `runs/<regress_run_id>/` with:
- `regression_report.json` (schema: `docs/schemas/regression_report.schema.json`)
- linked diff artifacts from `paperfig diff`

The report compares accepted counts, average score, and traceability coverage, and evaluates
invariants that flag regressions.
