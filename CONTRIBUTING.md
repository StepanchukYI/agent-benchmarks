# Contributing to agent-benchmarks

Thanks for your interest. This project is invite-only friends-first (ADR-006). Patches welcome from invited collaborators.

## Ground rules

1. **Privacy boundary** (LSN-006). Do not commit personal vault content, real API keys, real account names, or paths from a maintainer's home directory. CI has a privacy scanner; trajectories failing `privacy_check` are blocked from publish.
2. **Trajectory protocol** (`docs/trajectory-protocol.md`) is a contract. Runners normalize into the shared format. Do not add a runner that emits a non-uniform trajectory.
3. **LLM-judge alone is not a scorer**. Always pair LLM-judge with at least one deterministic check (LSN-004).
4. **ADRs are authoritative**. If a change contradicts an ADR, write a new ADR in vault `Projects/agent-benchmarks/decisions.md` first.
5. **Backward-compatible reads**. Never drop fields from dataset / trajectory / submission schemas. Extend, then deprecate.

## Local setup

```bash
make install        # uv sync (Python workspace) + pnpm install (TS)
make test           # pytest + vitest
make lint           # ruff + eslint + prettier
make typecheck      # mypy + tsc
```

## PR checklist

- [ ] Tests added or updated (unit + contract where relevant).
- [ ] Lint + typecheck clean locally.
- [ ] If schema changed: `make schema-export` and commit the diff under `docs/schemas/`.
- [ ] If a new ADR is implied: write it in the vault and link.
- [ ] If touching trajectory format: bump `ab-sdk` minor version.
- [ ] No live model API calls in CI.

## Issue templates

- New task — `.github/ISSUE_TEMPLATE/new-task.md`
- New model adapter — `.github/ISSUE_TEMPLATE/new-model-adapter.md`
- New config tier — `.github/ISSUE_TEMPLATE/new-config-tier.md`
- Bug — `.github/ISSUE_TEMPLATE/bug.md`

## Code of Conduct

`CODE_OF_CONDUCT.md`. Be kind. Disagree on the substance, not the person.
