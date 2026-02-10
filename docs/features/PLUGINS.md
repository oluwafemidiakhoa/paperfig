# Plugin Registry

## Plugin Types
The registry exposes two built-in plugin kinds:
- `critique_rule` for architecture critique rules
- `repro_check` for reproducibility audit checks

Each plugin has a descriptor validated against
`docs/schemas/plugin_descriptor.schema.json`.

## CLI
List plugins:

```bash
paperfig plugins list
```

Validate the registry:

```bash
paperfig plugins validate
```

## Run Artifacts
Each run records active plugins in `runs/<run_id>/plugins.json`.
