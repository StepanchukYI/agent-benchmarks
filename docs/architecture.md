# Architecture

High-level overview of the `agent-benchmarks` monorepo. Authoritative detail lives in the vault project hub and the build spec.

## Reference docs

- Vault: `Projects/agent-benchmarks/hub.md` — current project status, active ADRs.
- Vault: `Projects/agent-benchmarks/decisions.md` — ADRs 001–008 (authoritative).
- Build spec: `agent_benchmarks_build_spec.md` (companion to this repo) — source of truth for layout, schemas, and phase deliverables.
- PRD: `agent_benchmarks_PRD.md`.

## Packages

The repo is a `uv` Python workspace plus a `pnpm` TypeScript workspace. Six packages.

- **`ab-datasets`** (Python). Pydantic schemas for tasks, fixtures, scorer chains, and tier manifests. Holds the actual task YAML files organized by layer (L0–L5), plus fixtures (config tiers, vault snapshots, test repos, MCP mocks).
- **`ab-harness`** (Python). Runs a task against a model. Owns the trajectory protocol, the runner adapters (Claude Code, Codex CLI, Gemini CLI, GLM, MiniMax), the deterministic and LLM-judge scorers, the Docker sandbox that materializes a tier, and reporting helpers.
- **`ab-server`** (Python, FastAPI). REST API + background pull-fetcher that aggregates results from registered GitHub repos (ADR-007). Stores users, repos, runs, task results, submissions, scorer verdicts, and tier registry in Postgres.
- **`ab-leaderboard`** (TypeScript, React + Vite). The web app. Five surfaces: Leaderboard matrix, Run Launcher, Trajectory Viewer, Trends, Settings.
- **`ab-sdk`** (Python). Lightweight library shared by the CLI, harness, and server. Reads and writes the `results/<run-id>/` directory format, validates trajectories, and writes `metadata.yaml`.
- **`ab-cli`** (Python, Typer). The user-facing `ab` command. Registers repos via GitHub OAuth device flow, runs suites, publishes results to a contributor repo, replays remote commits, and (P7) drives the L5 evolved-config loop.

## Cross-cutting concerns

### Trajectory protocol

A single append-only JSONL format (`docs/trajectory-protocol.md`) is the contract between every runner and every consumer. Each line is one event — `run_start`, `turn`, `scorer`, or `run_end`. Runners normalize their model-specific output into this shape. Deterministic scorers must be re-runnable from the file alone; that property is what allows the server to re-score submissions and award a `verified` trust tier (LSN-007).

### Initial config tiers

A `Tier` (T0 vanilla, T1 minimal, T2 personal, T3 full — see `docs/config-tiers.md`) is a content-addressed bundle of CLAUDE.md, skills, MCP configs, and a vault snapshot that the sandbox materializes before a task runs. Its `tier_hash` is recorded in `run_start`. Every task declares `required_tier` and optional `also_run_on`, so the same task can be compared head-to-head across tiers (ADR-008).

### Trust tiers

Every submission carries a `trust_tier` (`self_reported` / `verified` / `official` — see `docs/trust-tiers.md`). `verified` is awarded by the server only when its re-score of the trajectory matches the self-reported numbers within tolerance. `official` is reserved for runs the server itself executed. Per-layer ceilings prevent overclaiming on tasks whose scorers cannot be re-run from the trajectory alone (ADR-007, LSN-005).

### Privacy boundary

Three enforcement layers (LSN-006): a pre-commit hook in contributor repos, a `privacy_check` scorer inside every publishable trajectory, and the `privacy-scan` CI workflow at the repo level. The pattern set lives in `docs/privacy-patterns.yaml`. Public datasets ship via `ab-datasets`; sensitive tasks stay in a laptop-only `ab-datasets-private` sibling package that is `.gitignored` from any public remote.
