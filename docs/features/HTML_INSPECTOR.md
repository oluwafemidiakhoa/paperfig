# HTML Inspector

## Usage
Generate a self-contained inspector for a run:

```bash
paperfig inspect <run_id> --html
```

## Artifacts
The inspector writes:
- `runs/<run_id>/inspect/index.html`
- `runs/<run_id>/inspect/manifest.json`

The manifest schema is documented at `docs/schemas/inspect_html.schema.json`.

The HTML bundles figures, traceability, critique summaries, repro audit data, and diffs into a
single static page.

## Notes
The inspector reads existing run artifacts. If `inspect.json` is missing, `paperfig inspect --html`
will rebuild it before rendering.
