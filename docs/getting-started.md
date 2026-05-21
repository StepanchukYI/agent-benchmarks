# Getting started — your first benchmark in 15 minutes

This guide walks a friend operator from `git clone` to a verified score on the leaderboard. Bash + macOS / Linux. If anything below assumes a tool you don't have, hit the **Prereqs** section.

## TL;DR

```bash
git clone git@github.com:StepanchukYI/agent-benchmarks.git
cd agent-benchmarks
make install

# Pick ONE: mock dry-run OR real run
make demo-mock              # local-only, no API key needed
make demo-claude-code       # requires `claude` CLI + ANTHROPIC_API_KEY
```

Either path emits `<results_root>/<utc>-<runid>/` with a valid `trajectory.jsonl`, `scores.json`, and `metadata.yaml`. By default `results_root` is `~/.ab/results` (kept outside the repo so runners like Claude Code don't auto-discover the parent `CLAUDE.md` / skills / MCPs). Pass `--results-root <path>` to override — CI and the Makefile demo targets pin an explicit path.

## Prereqs

| Tool | Why | Install |
|---|---|---|
| Python 3.11+ | runs ab-server, ab-cli, ab-harness | `brew install python@3.11` or use `uv` to manage |
| `uv` | workspace + venv manager | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node 20+, `pnpm` 9+ | runs ab-leaderboard SPA | `brew install node pnpm` |
| `git` | obvious | `xcode-select --install` on macOS |
| `claude` CLI | only for `--runner claude-code` | https://docs.claude.com/claude-code (TBC) |
| `ANTHROPIC_API_KEY` | only for `--runner claude-code` | `export ANTHROPIC_API_KEY=sk-ant-...` |
| `codex` CLI | only for `--runner codex-cli` (P1.7) | https://github.com/openai/codex |
| `opencode` CLI | only for `--runner opencode` (P1.8) | https://github.com/sst/opencode |
| Docker (optional) | needed if you want sandboxed runs (P4) | https://docs.docker.com/get-docker/ |

`make install` runs `uv sync` (Python workspace) + `pnpm install` (TypeScript workspace).

## Path 1 — local dry-run (no API key)

Use this to verify the harness works end-to-end without spending any money.

```bash
uv run ab task list                                  # 5+ L0 tasks visible
uv run ab task validate packages/ab-datasets/ab_datasets/L0_foundation/
uv run ab task dry-run L0_001                        # loads task + checks fixtures

# Run all L0 tasks with the deterministic MockRunner
uv run ab run --suite L0_smoke --runner mock --tier T0 --results-root ./results
```

Expected output:

```
pass L0_001 tier=T0 score=1.000 -> ./results/<utc>-<runid>
fail L0_002 tier=T0 score=0.5   -> ...
fail L0_003 tier=T0 score=0.333 -> ...
fail L0_004 tier=T0 score=0.333 -> ...
fail L0_005 tier=T0 score=0.5   -> ...
```

Mock fails most because it doesn't actually create files; scorers correctly catch that. That's the framework working, not a bug.

Then verify the run dir is spec-conforming:

```bash
ls ./results/*
# trajectory.jsonl scores.json metadata.yaml workdir/

uv run python -c "
from ab_sdk.results import validate
from pathlib import Path
for rd in Path('./results').iterdir():
    issues = validate(rd)
    print(rd.name, 'ok' if not issues else issues)
"
```

## Path 2 — real run against Claude Code

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# Single task first to keep cost low
uv run ab run --task L0_001 --runner claude-code --model claude-sonnet-4-5 --tier T0 --results-root ./results

# Once you trust the setup, run the whole L0 smoke suite
uv run ab run --suite L0_smoke --runner claude-code --model claude-sonnet-4-5 --tier T0
```

Each task spawns `claude` in headless `stream-json` mode and writes a trajectory. The scorer chain runs after the model finishes. Total cost for L0_smoke (5 tasks, sonnet 4.5) is in the cents.

## Publish to the leaderboard

To compare your runs with friends, register a public results repo and push:

```bash
# 1. One-time: register an empty public GitHub repo as your results sink
uv run ab register https://github.com/<you>/ab-results --server http://localhost:8000

# The CLI prints a code + URL; open it in a browser, paste the code, approve.
# Token is cached in $XDG_CONFIG_HOME/agent-benchmarks/credentials.json (mode 0600).

# 2. After every batch of runs, push them
uv run ab publish --server http://localhost:8000
```

`ab publish` runs the privacy gate first (no API keys / maintainer paths leak into the trajectory), then `git clone`s the cached results repo, copies new `results/<id>/` dirs in, commits + pushes.

The local ab-server (or the production deployment, once a hosting target is chosen — see ADR-007) polls the registered repo every 15 minutes, ingests new submissions, re-runs the deterministic scorer chain in replay mode, and marks the row `trust_tier=verified` if the rescored total matches your self-reported total within 1%.

## See your runs in the UI

```bash
# Boot the local stack (Postgres + ab-server + ab-leaderboard) via docker compose
make dev-up

# Or run server + UI directly
cd packages/ab-server && uv run alembic upgrade head && uv run uvicorn ab_server.main:app --reload &
cd packages/ab-leaderboard && AB_API_BASE_URL="http://localhost:8000/api/v1" pnpm dev
```

Open http://localhost:5173/leaderboard. With an empty DB the UI shows "No verified runs yet" empty state; after `ab publish` (and a 15-min poll cycle, or `POST /repos/{id}/sync` to force a refresh), your model row appears.

```bash
# Force a sync from CLI for testing — bypasses 15-min poll cycle
curl -X POST http://localhost:8000/api/v1/repos/<repo-id>/sync \
  -H "X-Test-User: alice"
```

## Daily workflow

Most operators iterate locally and only push milestone results:

```bash
# Iterate on a task YAML
$EDITOR packages/ab-datasets/ab_datasets/L1_memory/L1_001-...yaml
uv run ab task validate packages/ab-datasets/ab_datasets/L1_memory/L1_001-...yaml
uv run ab run --task L1_001 --runner mock --tier T0

# Confident? Run for real on the model you want to evaluate
uv run ab run --task L1_001 --runner claude-code --model claude-sonnet-4-5

# Publish
uv run ab publish
```

## What's NOT implemented in v1 (per [build spec](../agent_benchmarks_build_spec.md) §5)

| Feature | Status | Workaround |
|---|---|---|
| CodexCLIRunner | stub (P1.7) | use `--runner mock` or `--runner claude-code` for now |
| OpenCodeRunner | stub (P1.8) | same |
| ClaudeDesktopRunner | not started | not on roadmap for v1 |
| Server-side run dispatch via POST /runs | scheduled-record only | use `ab run` CLI locally; the "Launch run" button in the UI shows a copy-able CLI command |
| Background fetcher worker | sync-inside-request | manual `POST /repos/{id}/sync` for now |
| Real LLM-judge ensemble | stub (P2) | only deterministic scorers run today; no scorer chain depends on llm_judge |
| Docker sandbox runtime | host execution only | runs happen in your shell with the task fixture seeded into a workdir; sandbox=docker comes in P4 |
| Inspect AI integration | not wired (P4) | ADR-001 promises this; harness orchestrator uses direct subprocess for now |
| GitHub OAuth App (real) | placeholder client_id | `ab register` works against a self-hosted dev server; production OAuth App needs to be created before v1 ship |

When you hit any of these, the doc next to the relevant package directory should tell you exactly what's missing. If it doesn't, please open an issue.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `claude: command not found` | Claude Code CLI not installed | install per https://docs.claude.com/claude-code |
| `make install` fails on pnpm | Node version too old | `nvm install 20 && nvm use 20` |
| `ab publish` fails "privacy-gate" | A trajectory contains a token / maintainer path | inspect `results/<id>/trajectory.jsonl`, redact, rerun the task |
| `ab register` opens browser but token doesn't return | Local server can't reach `github.com/login/oauth/access_token` from your network | set `AB_HTTP_TIMEOUT=60`, retry. Corporate proxy? export `HTTPS_PROXY=...` |
| Leaderboard shows "No verified runs yet" after publish | Fetcher hasn't run | `curl -X POST .../repos/<id>/sync -H "X-Test-User: alice"` (dev) or wait 15 min |
| Schema mismatch errors in pytest | You modified Pydantic schemas | `make schema-export` and commit the diff under `docs/schemas/` |

## Where to go next

- `agent_benchmarks_build_spec.md` — full architecture + phase plan
- `docs/architecture.md` — package-by-package walkthrough
- `docs/trajectory-protocol.md` — JSONL event contract (§6)
- `docs/config-tiers.md` — T0/T1/T2/T3 (ADR-008)
- `docs/trust-tiers.md` — self_reported / verified / official
- `docs/adding-a-task.md` — contribute a new benchmark task
- `docs/adding-a-model-adapter.md` — wrap a new agent harness
- `CLAUDE.md` — project guide for Claude Code sessions
