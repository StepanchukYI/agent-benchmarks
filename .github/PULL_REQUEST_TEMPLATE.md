## Summary

What changed and why. One paragraph.

## PR checklist

- [ ] Tests added or updated (unit + contract where relevant).
- [ ] `ruff check` and (where relevant) `eslint` + `prettier` clean locally.
- [ ] Typecheck clean: `mypy packages` (advisory in Phase 0) and `pnpm typecheck`.
- [ ] If schema changed: ran `make schema-export` and committed the diff under `docs/schemas/`.
- [ ] If a new ADR is implied: written in vault `Projects/agent-benchmarks/decisions.md` and linked below.
- [ ] If touching trajectory format: bumped `ab-sdk` minor version.
- [ ] No live model API calls in CI (all adapter tests use recorded fixtures).
- [ ] `python scripts/privacy_scan.py` passes locally.

## ADR / vault links

- ADR (if any):
- Vault doc (if any):

## Notes for reviewers

Optional context, screenshots, or trade-offs considered.
