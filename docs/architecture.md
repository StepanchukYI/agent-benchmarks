# Architecture

High-level architecture of the `agent-benchmarks` monorepo. Authoritative ADRs live in the vault (`Projects/agent-benchmarks/decisions.md`).

Companion docs in this folder:
- `prd.md` — product requirements (what we are building and why)
- `roadmap.md` — phase timeline and current status
- `trajectory-protocol.md` — append-only JSONL contract
- `trust-tiers.md` — self-reported / verified / official semantics
- `config-tiers.md` — T0/T1/T2/T3 sandbox materialization
- `result-sensitivity-axes.md` — leaderboard pillar definitions

---

## Repo layout

```
agent-benchmarks/
├── packages/
│   ├── ab-datasets/      # Python — task YAMLs, schemas, fixtures
│   ├── ab-harness/       # Python — runners, scorers, sandbox, trajectory
│   ├── ab-server/        # Python (FastAPI) — REST API, fetcher, re-scoring
│   ├── ab-leaderboard/   # TypeScript (React + Vite) — web app
│   ├── ab-sdk/           # Python — shared run-dir read/write helpers
│   └── ab-cli/           # Python (Typer) — `ab` CLI
├── docs/                 # Contributor-facing documentation
├── infra/                # docker-compose, terraform, deploy manifests
├── tests-e2e/            # Cross-package contract tests
└── scripts/              # privacy_scan, run_quick, run_matrix, serve_local
```

`uv` Python workspace + `pnpm` TypeScript workspace. Six packages, all in one repo by ADR-005. Trigger for multi-repo split: first external submission accepted (extract `ab-server` + `ab-sdk`) or HF Hub publication (extract `ab-datasets`).

---

## Package responsibilities

### `ab-datasets`
Pydantic schemas + task YAML corpus + fixtures.

- `ab_datasets/schemas/` — Task, Trajectory, Tier, ScorerVerdict, Submission, AgentConfig models. Exported as JSON Schema via `make schema-export` → `docs/schemas/*.schema.json`.
- `ab_datasets/L<N>_<theme>/` — task YAMLs per layer (L0 foundation, L1 memory, L2 skill router, L3 system-specific, L4 composite, L5 evolved).
- `fixtures/repos/L<N>_smoke/L<N>_<id>/` — per-task repo fixtures.
- `fixtures/config_tiers/{T0,T1,T2,T3}/` — tier bundles materialized into the sandbox before a run.
- `fixtures/vault_snapshots/` — anonymized Obsidian vault snapshots for L3a memory tasks.

### `ab-harness`
Runs a task against a model. Owns the operational contracts.

- `runners/` — model adapters. Each inherits from `BaseRunner` and normalizes model-specific output into the shared trajectory protocol. Shipped: `claude-code`, `codex-cli`, `gemini-cli`, `opencode`, `pi-agent`, `anthropic-compat` (GLM/MiniMax/Moonshot/DeepSeek vendor routing), `openai-compat`, `local`, `mock`.
- `runners/_isolation.py` — `IsolatedEnv` whitelist-based subprocess env build + optional fake HOME. Prevents operator env leak into benchmark subprocess. `claude-code` uses `use_fake_home=False` to keep Max-subscription keychain access.
- `scorers/` — deterministic, schema, exec, llm-judge, state-diff, privacy-check. Each scorer exposes `.run(workdir, task)` (live) AND `.replay(traj_path, task)` (trajectory-only) to enable the `verified` trust tier (LSN-007).
- `scorers/track_b_scorers.py` — assertion-chain wrapper covering 79 named scorers from Track B's task YAMLs. Single engine, per-name dispatch via `_make_assertion_scorer`.
- `scorers/assertions.py` — assertion library (workdir_file_*, tool_args_match_schema, citation checks, etc.).
- `sandbox/` — materializes a tier (T0/T1/T2/T3) into a Docker container before the run. Hash-pinned bundles for re-runnability.
- `trajectory/` — writer / reader / validate. Enforces append-only JSONL, exactly-one `run_start` (first event) + `run_end` (last event), strictly monotonic `turn.idx` from 0.
- `models.py` — registry of 32+ hosted models + 19+ local models, vendor base URLs.

### `ab-server`
FastAPI service + background fetcher worker.

- `api/` — REST endpoints under `/api/v1/`. Auth (GitHub device flow + session_token cookie), repos, runs, submissions, leaderboard, trends, alerts, jobs, presets, tokens, tasks, tiers, account, system.
- `fetcher/` — background worker that polls registered GitHub repos for new `results/<run-id>/` directories. Pull-based aggregation (ADR-007) — server pulls from contributor repos rather than push.
- `rescoring/` — re-runs deterministic scorers from the trajectory alone after a submission lands. Tolerance-checks self-reported vs. server-rescored numbers; awards `verified` trust tier if within tolerance.
- `leaderboard/` — query builder + ranking. Supports filter axes: suite, model, operator, trust_tier, dataset_version, task_tag, date range, pillar (correctness / tool_skill / context_efficiency / latency_cost / memory_specific).
- `alerts/` — user-configured regression alerts evaluated on the trends pipeline.
- `models/` — SQLModel ORM. Tables: users, repos, runs, task_results, submissions, scorer_verdicts, tiers, alerts, jobs, presets, api_tokens.
- `alembic/versions/` — migrations. Linear chain through `0006_api_tokens.py` (mergepoint).

### `ab-leaderboard`
React SPA. Five surfaces: Leaderboard / Trends / Tasks / Runs / Trajectories / Settings.

- `src/api/{client,hooks}.ts` — react-query hooks per endpoint, normalization adapters for server response shapes (bare array vs `{items}` envelope).
- `src/components/` — shell (PageHero, SubNav, Filter), charts (TrendChart, ParetoTrail, ScoreHeatmap), settings tabs (Account, Repos, Tokens, Privacy).
- `src/pages/` — top-level surfaces with subtab routing per page.
- `src/lib/types.ts` — TypeScript shapes mirroring server response types.
- `src/lib/ui-state.ts` — `toState` helper folding loading/empty/error into one component-friendly state.

Designer agent (`frontend-design`) owns visual layout. Wiring (hooks, state, endpoints) owned by the platform agents.

### `ab-sdk`
Shared library used by CLI, harness, and server.

- `results.py` — read/write/validate the `results/<utc>-<runid>/` directory format. Each run directory holds `trajectory.jsonl`, `scores.json`, `metadata.yaml`.
- `publish_gate.py` — privacy + schema validation that runs before `ab publish` uploads to a contributor repo.
- `submission.py` — builds the `Submission` envelope sent to the server's `/submissions` endpoint.

### `ab-cli`
The `ab` command. Typer-based.

- `commands/run.py` — runs a single task. Picks a runner based on `--runner`, materializes the tier, executes, writes the run directory.
- `commands/wizard.py` — interactive picker (runner / model / effort / suite / tier).
- `commands/register.py` — GitHub OAuth device flow + register a contributor repo with the server.
- `commands/publish.py` — push the latest run to the contributor repo's results directory.
- `commands/replay.py` — re-execute scorers from a remote commit's trajectory.
- `commands/submit.py` — submit a published trajectory URL to a server.
- `commands/evolve.py` — drives the L5 evolved-config loop (P7).
- `commands/task.py` — `task list`, `task validate`, `task dry-run`.

---

## Cross-cutting concerns

### Trajectory protocol

Append-only JSONL. Exactly one `run_start` (first event) + one `run_end` (last). Strictly monotonic `turn.idx` from 0. Scorer events strictly after the last turn. Tool calls / returns are non-null arrays. `ab_harness.trajectory.validate` enforces every invariant.

A single shape is the contract between every runner and every consumer. Runners normalize INTO the protocol; the protocol does not bend to a model. Deterministic scorers re-run from this file alone; that is what enables the `verified` trust tier from a third-party submission.

See `docs/trajectory-protocol.md` for the full event grammar.

### Config tiers (T0 / T1 / T2 / T3)

Per ADR-008, initial agent configuration is a first-class benchmark axis. A `Tier` is a content-addressed bundle (CLAUDE.md + skills + MCP configs + vault snapshot) that the sandbox materializes before the task starts. Its `tier_hash` is recorded in `run_start`.

- **T0 vanilla** — no project context. Just the bare runner + the task input.
- **T1 minimal** — minimal CLAUDE.md + 2-3 essential skills, no vault.
- **T2 personal** — anonymized maintainer config: CLAUDE.md, skills, MCP configs, vault snapshot.
- **T3 full** — T2 + every plugin/skill the maintainer's daily setup carries.

Tasks declare `required_tier` and optional `also_run_on`. The same task can be compared head-to-head across tiers. See `docs/config-tiers.md`.

### Trust tiers

`self_reported` / `verified` / `official` (see `docs/trust-tiers.md`).

- **self_reported**: contributor's own numbers, no server verification.
- **verified**: server re-ran deterministic scorers from the trajectory and matched within tolerance. Requires every scorer in the chain to be replay-capable (LSN-007).
- **official**: the server itself executed the run end-to-end.

Per-layer ceilings prevent overclaiming when scorers genuinely cannot be re-run from the trajectory alone (e.g. L3 private, L4 composite). See ADR-007 + LSN-005.

### Privacy boundary

Three enforcement layers (LSN-006):

1. Pre-commit hook in contributor repos
2. `privacy_check` scorer inside every publishable trajectory
3. `privacy-scan` CI workflow at the repo level

Pattern set in `docs/privacy-patterns.yaml`. Public datasets ship via `ab-datasets`. Sensitive tasks live in the `ab-datasets-private` sibling package that is `.gitignored` from any public remote.

### Isolation (Max-subscription benchmark runs)

`runners/_isolation.py::IsolatedEnv` builds the subprocess env from a whitelist, optionally with a fake HOME. The `claude-code` runner passes `use_fake_home=False` so the macOS Keychain "Claude Code-credentials" entry remains accessible — required for Max-subscription auth without an API key.

For honest isolation (no operator-CLAUDE.md leak into the benchmark run), set `AB_CLAUDE_HIDE_USER_CONFIG=1`. The runner temp-renames `~/.claude/{CLAUDE.md, skills/, agents/, plugins/, memory/, commands/, hooks/}` to `<path>.ab-benchmark-hidden` for the duration of the run, with atexit restoration.

---

## Data flow — `ab run` end-to-end

```
ab run --suite L0_smoke --task L0_001 --runner claude-code --tier T0
         │
         ├─► load Task YAML from ab-datasets
         ├─► resolve fixture dir
         ├─► materialize Tier T0 bundle into sandbox workdir
         ├─► spawn runner subprocess via IsolatedEnv
         │       │
         │       └─► model emits stream-json events
         │       └─► runner adapter normalizes → trajectory.jsonl
         │
         ├─► run scorer chain (deterministic + privacy_check + tool_skill + ...)
         │       │
         │       └─► each scorer writes ScorerVerdict event into trajectory
         │
         ├─► finalize trajectory.jsonl (append run_end)
         ├─► write scores.json (per-pillar + total)
         └─► write metadata.yaml (model, effort, tier_hash, dataset_version)
                 │
                 └─► results/<utc>-<runid>/ ready for `ab publish`
```

`ab publish` pushes the run directory to the contributor's registered GitHub repo. The server's fetcher worker discovers it on next poll, validates against schemas, re-runs deterministic scorers, awards the trust tier, and writes the row to the leaderboard.

---

## Where to look

| What you're touching | Authoritative path |
|---|---|
| Task YAMLs | `packages/ab-datasets/ab_datasets/L<N>_*/` |
| Pydantic schemas | `packages/ab-datasets/ab_datasets/schemas/` |
| Runners | `packages/ab-harness/ab_harness/runners/` |
| Scorers | `packages/ab-harness/ab_harness/scorers/` |
| Trajectory | `packages/ab-harness/ab_harness/trajectory/` |
| Sandbox | `packages/ab-harness/ab_harness/sandbox/` |
| Server endpoints | `packages/ab-server/ab_server/api/` |
| ORM | `packages/ab-server/ab_server/models/` |
| Migrations | `packages/ab-server/alembic/versions/` |
| Fetcher / re-scoring | `packages/ab-server/ab_server/{fetcher,rescoring}/` |
| FE pages / hooks | `packages/ab-leaderboard/src/{pages,api}/` |
| CLI commands | `packages/ab-cli/ab_cli/commands/` |
| Run dir contract | `packages/ab-sdk/ab_sdk/results.py` |
| Publish gate | `packages/ab-sdk/ab_sdk/publish_gate.py` |
