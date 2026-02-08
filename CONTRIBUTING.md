# Contributing

Thanks for contributing to `paperfig`. This project is architecture-first and artifact-driven: code changes should keep docs, flows, prompts, and run artifacts coherent.

## Development Setup
```bash
pip install "paperfig[cli,png,dev,yaml,pdf,mcp]"
./scripts/check_quality.sh
```

## Contributing Ladder
Pick the smallest useful rung and open a focused PR:

1. Add a new YAML flow template in `paperfig/templates/flows/`.
2. Add or improve a flow doc and Mermaid diagram in `docs/architecture/flows/`.
3. Improve a critique or planning prompt in `paperfig/prompts/`.
4. Add a reproducibility audit rule in `paperfig/audits/reproducibility.py`.
5. Add a domain template pack (for example bio/robotics/medical imaging).

## PR Requirements
- Keep behavior traceable and deterministic where possible.
- Update architecture docs when design or flow changes.
- Include tests for changed behavior.
- Ensure `./scripts/check_quality.sh` passes.
- Keep CI logic in `scripts/` and use workflow YAML as thin wrappers only.

## Commit and PR Style
- Use clear commit messages (what changed and why).
- Keep PR scope focused and reviewable.
- Document tradeoffs and known limitations in PR description.

## Security and Safety
- Do not commit secrets, API keys, or private datasets.
- Respect sandbox and policy constraints for autonomous lab execution.
