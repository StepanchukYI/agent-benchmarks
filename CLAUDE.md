vault_hub: Projects/agent-benchmarks

# agent-benchmarks — Project Guide for Claude Sessions

## Identity (L0)

Multi-layer benchmark harness for coding agents (Claude Code, Codex CLI, Gemini CLI, GLM, MiniMax) across foundation skills, memory write-in-flight, MCP/skill triggering, and domain integrations. Modular monorepo, 6 packages. OSS Apache-2.0, friends-first.

**Authoritative spec**: `agent_benchmarks_build_spec.md` in this repo root. If anything in this file contradicts the build spec, the build spec wins.

**Vault hub**: `Projects/agent-benchmarks/hub.md` (decisions, lessons, status). Memory skill loads automatically at session start via the `vault_hub:` directive above.

## Read-first checklist

When you start a session on this repo:

1. Load vault via `memory:memory-session` (the global CLAUDE.md already mandates it).
2. Skim `agent_benchmarks_build_spec.md` §5 for phase/row status.
3. `git log --oneline -10` to see recent commits.
4. `uv run pytest -q` to confirm baseline (current count = 100s, all passing).
5. `uv run ab task list` to see shipped tasks.

## Active ADRs (full text in vault)

001 Inspect AI · 002 6-layer architecture · 003 single-user start (partially superseded by 005) · 004 web app · 005 modular monorepo · 006 open source Apache 2.0 · 007 GitHub OAuth + pull-based aggregation · 008 config tiers (T0/T1/T2/T3) as first-class axis.

Active lessons that bite back: LSN-004 (LLM-judge alone is not a scorer), LSN-006 (privacy boundary three layers), LSN-007 (verified trust = re-runnable from trajectory alone).

## What ships and what doesn't (as of last commit)

- Phase 0 scaffold: done.
- Phase 1 M1 (local run path): done.
- Phase 1 M2 (publish + server): in progress.
- Phase 1 M3 (frontend): handed to `claude-designer` agent. Don't touch `packages/ab-leaderboard/src/` unless explicitly asked.

## Codebase map (where to look)

| What | Where |
|---|---|
| Task YAMLs | `packages/ab-datasets/ab_datasets/L0_foundation/`, `L1_memory/`, … |
| Pydantic schemas (Task, Trajectory, Tier, ScorerVerdict, …) | `packages/ab-datasets/ab_datasets/schemas/` |
| Runners (ClaudeCodeRunner, MockRunner, BaseRunner ABC) | `packages/ab-harness/ab_harness/runners/` |
| Trajectory writer/reader/validate | `packages/ab-harness/ab_harness/trajectory/` |
| Scorers + registry + chain runner | `packages/ab-harness/ab_harness/scorers/` |
| Sandbox tier materialize | `packages/ab-harness/ab_harness/sandbox/` |
| Tier fixtures | `packages/ab-datasets/fixtures/config_tiers/{T0_vanilla,T1_minimal,T2_personal,T3_full}/` |
| Vault snapshots | `packages/ab-datasets/fixtures/vault_snapshots/` |
| Run dir spec (read/write/validate) | `packages/ab-sdk/ab_sdk/results.py` |
| Publish gate (privacy + schema) | `packages/ab-sdk/ab_sdk/publish_gate.py` |
| FastAPI app, routes, models, alembic | `packages/ab-server/ab_server/` |
| React SPA | `packages/ab-leaderboard/src/` (designer-owned) |
| CLI commands | `packages/ab-cli/ab_cli/commands/{register,run,publish,replay,submit,evolve,task}.py` |
| End-to-end CLI test | `packages/ab-cli/tests/test_run_end_to_end.py` |
| Cross-package smoke | `tests-e2e/test_phase0_smoke.py` |

## Conventions to honor

- **Privacy boundary** (LSN-006). Three layers: pre-commit hook + `privacy_check` scorer + CI `privacy-scan` workflow. Patterns in `docs/privacy-patterns.yaml`. Never commit maintainer paths, real emails, or API tokens — CI will reject.
- **Trajectory contract** (build spec §6). Append-only JSONL. Exactly one `run_start` (first) + one `run_end` (last). Strictly monotonic `turn.idx` from 0. Scorers strictly after the last turn. Tool calls/returns are non-null arrays. `ab_harness.trajectory.validate` enforces all of this.
- **Re-runnable scorers** (LSN-007). Every deterministic scorer must expose BOTH `.run(workdir, task, ...)` (live workdir) AND `.replay(traj_path, task, ...)` (trajectory-only). Otherwise it can never enable `verified` trust tier.
- **No LLM-judge alone** (LSN-004). Always pair LLM-judge with at least one deterministic scorer in a chain.
- **pytest import mode** = `importlib` (root pyproject.toml). Each package has its own `tests/__init__.py`; without importlib mode you get `ModuleNotFoundError: tests.test_X` collisions.
- **Ruff `B008` is per-file-ignored** for `packages/ab-cli/ab_cli/commands/**` — Typer defaults call `typer.Option(...)` in argument signatures by design.
- **Schemas export** via `make schema-export` regenerates `docs/schemas/*.schema.json`. CI diffs the output; commit regenerated schemas with any model change.

## Workflows by intent

### "I want to add a new task"
1. Read `docs/adding-a-task.md`.
2. Write YAML under the right layer dir: `packages/ab-datasets/ab_datasets/L<N>_<theme>/L<N>_NNN-<slug>.yaml`.
3. Add fixtures under `packages/ab-datasets/fixtures/repos/L<N>_smoke/L<N>_NNN/` if the task needs input files.
4. `uv run ab task validate <path>` → must exit 0.
5. `uv run ab task dry-run L<N>_NNN` → must exit 0.
6. `uv run pytest packages/ab-datasets/tests/test_pilot_tasks.py` → must pass (universal task linter).
7. Smoke with the mock runner: `uv run ab run --task L<N>_NNN --runner mock --tier T0`.

### "I want to add a new runner"
1. Read `docs/adding-a-model-adapter.md`.
2. Inherit from `ab_harness.runners.base.BaseRunner`.
3. Normalize the model's output into the shared trajectory protocol — never invent a new trajectory shape.
4. Register in `packages/ab-harness/ab_harness/runners/__init__.py` and `_make_runner` in `packages/ab-cli/ab_cli/commands/run.py`.
5. Add VCR-style recorded HTTP fixtures (no live model calls in CI).

### "I want to add a new scorer"
1. Implement under `packages/ab-harness/ab_harness/scorers/`.
2. Expose BOTH `run` and `replay` returning `ScorerVerdict`. If replay genuinely impossible from trajectory alone, return `replay_unsupported` verdict.
3. Register in `SCORER_REGISTRY` (`packages/ab-harness/ab_harness/scorers/__init__.py`).
4. Add tests under `packages/ab-harness/tests/test_scorer_<name>.py` covering pass + fail + replay.

### "I want to change a Pydantic schema"
1. Edit under `packages/ab-datasets/ab_datasets/schemas/`.
2. Run `make schema-export` and commit the regenerated `docs/schemas/*.schema.json`.
3. **Extend, never remove** fields (build spec §12). Backward-compatible reads forever.

### "I want to ship something"
1. `uv run pytest -q` → all green.
2. `uv run ruff check .` → clean.
3. `uv run python scripts/privacy_scan.py` → exit 0.
4. `cd packages/ab-leaderboard && pnpm typecheck && pnpm build` → clean (unless designer is mid-work).
5. Commit with conventional prefix + co-author trailer.
6. Push.

## Anti-patterns to avoid

- Don't invent ADRs in code. If you need a new architectural decision, write it in vault `Projects/agent-benchmarks/decisions.md` first.
- Don't add live model calls in CI. Ever.
- Don't break the trajectory protocol. Runners normalize INTO the protocol; the protocol does not bend to a model.
- Don't commit anything that fails `privacy_check`. Even in tests.
- Don't introduce a new dependency without checking it appears in build spec §2.
- Don't touch `packages/ab-leaderboard/src/` unless explicitly asked (designer agent owns it).

## Useful one-liners

```bash
# Add a tier, regenerate hashes
uv run python scripts/build_t2_seed.py

# Refresh schemas after touching Pydantic models
uv run python -m ab_datasets.schemas.export --out docs/schemas

# Local server up (SQLite dev)
cd packages/ab-server && uv run alembic upgrade head && uv run uvicorn ab_server.main:app --reload

# Tail a trajectory
jq -c . results/<utc>-<runid>/trajectory.jsonl | head

# Re-score a fetched submission (server-side helper, after M2.9)
uv run python -m ab_server.rescoring.engine --submission-id <uuid>
```

## When in doubt

Reach for the build spec first, the vault second, your training data never. The spec is the contract; the vault is the rationale; this file is the cheat sheet.
