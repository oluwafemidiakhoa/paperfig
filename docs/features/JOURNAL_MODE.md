# Journal Mode

## Usage
Run generation with a journal profile:

```bash
paperfig generate examples/sample_paper.md --mode journal:neurips
```

## Profiles
Profiles live in `paperfig/journals/profiles/` and are mirrored in `docs/journals/`.
They are validated against `docs/schemas/journal_profile.schema.json`.

The built-in profile `neurips` enforces:
- higher critique thresholds
- required figure kinds (methodology, system overview, results plot)
- stricter architecture/repro gates

## Artifacts
Runs created in journal mode persist:
- `journal_profile.json`
- `run.json` fields `journal_profile`, `quality_threshold`, `dimension_threshold`
