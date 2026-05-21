# agent-benchmarks

Multi-layer benchmark harness for coding agents — Claude Code, Codex CLI, Gemini CLI, GLM, MiniMax — across foundation skills, memory write-in-flight, MCP/skill triggering, and domain integrations (Obsidian, Lantern, Backstage, GitNexus, Graphify).

**Status**: Phase 0 (scaffolding). Source of truth = `agent_benchmarks_build_spec.md` + vault `Projects/agent-benchmarks/`.

License: Apache-2.0.

## Layout

| Package | Lang | Purpose |
|---------|------|---------|
| `packages/ab-datasets` | Python | Task YAML, fixtures, Pydantic schemas, validators |
| `packages/ab-harness` | Python | Runners, scorers, sandbox, trajectory protocol |
| `packages/ab-server` | Python | FastAPI: registered repos, fetcher, re-scoring, leaderboard |
| `packages/ab-leaderboard` | TS / React | Leaderboard, Run Launcher, Trajectory Viewer, Trends, Settings |
| `packages/ab-sdk` | Python | Result-format SDK (read/write run dirs, replay, manifest) |
| `packages/ab-cli` | Python | `ab register / run / publish / replay / submit / evolve` |

## Quick start (dev)

```bash
make install        # uv sync + pnpm install
make dev-up         # docker compose: Postgres + ab-server + ab-leaderboard
ab --help           # CLI ready
curl localhost:8000/healthz
open http://localhost:5173/leaderboard
```

## Docs

- [Build spec](agent_benchmarks_build_spec.md) — what to build, Phase 0–1
- `docs/architecture.md` — high-level architecture
- `docs/trajectory-protocol.md` — trajectory.jsonl contract
- `docs/config-tiers.md` — T0/T1/T2/T3 (ADR-008)
- `docs/trust-tiers.md` — self_reported / verified / official (ADR-007)
- `docs/adding-a-task.md` — contributor guide
- `docs/adding-a-model-adapter.md` — runner contract

## ADRs in force

001 Inspect AI · 002 6-layer architecture · 003 single-user start · 004 web app · 005 modular monorepo · 006 open source Apache 2.0 · 007 GitHub OAuth pull-based · 008 config tiers as first-class axis.

See vault `Projects/agent-benchmarks/decisions.md` for full text.
