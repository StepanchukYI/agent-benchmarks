# agent-benchmarks

Multi-layer benchmark harness for coding agents — Claude Code, Codex CLI, Gemini CLI, GLM, MiniMax — across foundation skills, memory write-in-flight, MCP/skill triggering, and domain integrations (Obsidian, Lantern, Backstage, GitNexus, Graphify).

License: Apache-2.0. Status: Phase 1 in progress (M1 local run path shipped, M2 publish+server in progress, M3 frontend handed to claude-designer agent). Source of truth = `agent_benchmarks_build_spec.md` + vault `Projects/agent-benchmarks/`.

---

## Quickstart — run your first benchmark in 60 seconds

Prereqs: Python 3.11+, Node 20+, `uv`, `pnpm`. macOS or Linux.

```bash
git clone git@github.com:StepanchukYI/agent-benchmarks.git
cd agent-benchmarks
make install                                   # uv sync + pnpm install

# Dry-run with the mock runner — no API key needed
uv run ab task list                            # see shipped tasks
uv run ab run --suite L0_smoke --runner mock --tier T0 --results-root ./results

ls results/                                     # 5 spec-conforming run dirs
```

### Interactive picker

```bash
uv run ab wizard
```

Walks numbered prompts: runner → model → effort → suite → tier → optional
task. Prints the equivalent `ab run` invocation and (optionally) executes
it. Use `--dry` to just print the command.

### Helper scripts

```bash
scripts/run_quick.sh                          # claude-sonnet × low × L0_smoke
MODEL=claude-haiku-4-5 EFFORT=high scripts/run_quick.sh L0_001

# Matrix: model × effort × task → /tmp/ab-matrix-<utc>/
MODELS="claude-sonnet-4-5 claude-haiku-4-5" \
EFFORTS="low high" \
TASKS="L0_001 L0_002 L0_003 L0_004 L0_005" \
  scripts/run_matrix.sh

# Local backend + leaderboard FE
scripts/serve_local.sh                        # API :8000, FE :5173
```

### Supported runners

```
claude-code        Anthropic Claude Code (claude CLI)
codex-cli          OpenAI Codex CLI (codex)
gemini-cli         Google Gemini CLI (gemini)
opencode           OpenCode CLI (opencode.ai)
pi-agent           Pi coding agent (pi.dev)
anthropic-compat   Zhipu / MiniMax / Moonshot / DeepSeek (HTTP)
openai-compat      OpenAI / any /v1/chat/completions vendor
local              Ollama / LM Studio / vLLM / llama.cpp
mock               No live calls — smoke only
```

### Vendor-routed Claude Code (Chinese vendors via `ANTHROPIC_BASE_URL`)

```bash
# GLM via claude-code scaffold:
uv run ab run --suite L0_smoke --task L0_001 --runner claude-code \
       --model GLM-5.1 --tier T0 \
       --vendor zhipu --env ANTHROPIC_AUTH_TOKEN=$GLM_API_KEY

# MiniMax via claude-code scaffold:
uv run ab run --suite L0_smoke --task L0_001 --runner claude-code \
       --model MiniMax-M2.7 --tier T0 \
       --vendor minimax --env ANTHROPIC_AUTH_TOKEN=$MINIMAX_API_KEY
```

`--vendor` resolves to the canonical base URL from
`ab_harness.models.VENDOR_BASE_URLS` (anthropic / zhipu / moonshot /
minimax / deepseek). Tokens never come from the shell — pass them via
`--env`.

### Publish to the live leaderboard

```bash
uv run ab register https://github.com/<you>/ab-results --server http://localhost:8000
uv run ab publish --server http://localhost:8000
```

Friend-flow walkthrough: [`docs/friend-onboarding.md`](docs/friend-onboarding.md).

---

## Self-hosting

Want to run the server + leaderboard on your own box behind a reverse proxy? See [`docs/deploy-homelab.md`](docs/deploy-homelab.md) — single-host `docker compose` deploy with Caddy auto-TLS, GitHub OAuth, and a `pg_dump` cron. Restore runbook in [`docs/restore-from-backup.md`](docs/restore-from-backup.md); helpers in `scripts/db-backup.sh` and `scripts/db-restore.sh`.

---

## What ships today

| Layer | Coverage | Tier support |
|---|---|---|
| L0 foundation | ~80 tasks (file ops, schema fill, exec, extract, niah/ruler, instruction follow, tool use, faithfulness, reasoning) | T0 + T2 + T3 |
| L1 memory | growing pilot | T2 |
| L2 skill router | growing pilot | T2 |
| L3 domains (obsidian, lantern, backstage, gitnexus, graphify) | obsidian pilot | T2 |
| L4 composite | pilot | T2 |
| L5 evolved | not yet | — |

Runners (all real impls):

- `claude-code` — Claude Code CLI in headless `stream-json` mode
- `codex-cli` — OpenAI Codex CLI (`codex exec --json`)
- `gemini-cli` — Google Gemini CLI (`gemini --output-format stream-json`)
- `opencode` — OpenCode CLI (`opencode run --format json`)
- `pi-agent` — Pi coding agent (`pi --mode json --print`)
- `anthropic-compat` — HTTP wire to Anthropic + Zhipu/MiniMax/Moonshot/DeepSeek
- `openai-compat` — HTTP wire to OpenAI + any /v1/chat/completions vendor
- `local` — Ollama / LM Studio / vLLM / llama.cpp / text-generation-webui
- `mock` — deterministic partial-credit, no live calls (CI safe)

Stubs only: `hermes-agent`, `nanobot`, `cursor`.

Scorers (deterministic, re-runnable from trajectory.jsonl alone — LSN-007): `file_diff`, `exec`, `schema` (jsonschema), `state_diff`, `privacy_check`, plus Track B's per-task assertion chains. Each scorer exposes `.run(workdir, task)` (live) and `.replay(traj_path, task)` (trajectory-only) — same verdict shape. LLM-judge available but always paired with at least one deterministic scorer (LSN-004).

Tiers (ADR-008): T0 vanilla · T1 minimal · T2 personal · T3 full. Materialized into the sandbox workdir; `tier_hash` recorded in `trajectory.run_start`.

Sensitivity axes recorded in every run (per `docs/result-sensitivity-axes.md`): `sampling` (temperature / top_p / max_output_tokens), `reasoning.effort`, `system_prompt_verbatim`, `model_context_window_tokens`, `output_truncated`, `turn_cap`.

---

## Repo layout

```
agent-benchmarks/
├── packages/
│   ├── ab-datasets/    Python — task YAMLs, fixtures, Pydantic schemas, loaders
│   ├── ab-harness/     Python — runners, scorers, sandbox, trajectory protocol
│   ├── ab-server/      Python — FastAPI (auth, repos, fetcher, rescoring, leaderboard)
│   ├── ab-leaderboard/ TS/React — SPA (5 pages, shadcn defaults)
│   ├── ab-sdk/         Python — read/write run dirs, publish gate, replay
│   └── ab-cli/         Python — `ab run / register / publish / task / replay`
├── docs/               architecture, trajectory protocol, tiers, trust tiers, privacy patterns,
│                       friend-onboarding, public deploy, sensitivity axes, model registry
├── infra/              docker-compose + Dockerfiles
├── scripts/            run_quick.sh, run_matrix.sh, serve_local.sh, privacy_scan.py,
│                       privacy_scrub.py, ingest_local_runs.py, build_t2_seed.py, db-{backup,restore}.sh
├── tests-e2e/          cross-package contract + e2e
├── agent_benchmarks_build_spec.md   AUTHORITATIVE BUILD SPEC
└── Makefile
```

---

## Workflow — make targets

```bash
make install           # uv sync + pnpm install
make dev-up            # docker compose: Postgres + ab-server + ab-leaderboard
make dev-down
make test              # pytest + vitest
make lint              # ruff + eslint
make typecheck         # mypy + tsc
make schema-export     # regen docs/schemas/*.schema.json from Pydantic
make privacy-scan      # docs/privacy-patterns.yaml across repo
make clean
```

---

## CLI tour

```bash
ab --help                                          # top-level
ab wizard                                          # interactive runner/model/effort picker
ab task list                                       # all shipped tasks
ab task validate packages/ab-datasets/ab_datasets/L0_foundation/
ab task dry-run L0_001                             # load + check fixture presence

ab run --suite L0_smoke --runner mock --tier T0
ab run --suite L0_smoke --runner claude-code --model claude-sonnet-4-5 --effort low --tier T2
ab run --suite L0_smoke --runner opencode    --model anthropic/claude-sonnet-4-5 --effort medium --tier T0
ab run --suite L0_smoke --runner pi-agent    --model claude-sonnet-4-5 --effort high  --tier T0
ab run --suite L0_smoke --runner codex-cli   --model gpt-5 --effort medium --tier T0
ab run --suite L0_smoke --runner gemini-cli  --model gemini-2.5-pro --effort medium --tier T0
ab run --task L0_003 --runner claude-code --tier T0

# Vendor-routed claude-code scaffold (Anthropic-compat layer):
ab run --suite L0_smoke --task L0_001 --runner claude-code \
       --model GLM-5.1 --tier T0 \
       --vendor zhipu --env ANTHROPIC_AUTH_TOKEN=$GLM_API_KEY

ab register https://github.com/<you>/ab-results   # GitHub device-flow + POST /repos
ab publish                                         # privacy-gate + commit + push
ab publish --dry-run                               # check without pushing

ab replay <run-id> <commit-sha>                    # server-side replay (M2.9)
ab submit                                          # legacy push (ADR-007 fallback)
ab evolve                                          # L5 auto-evolution (Phase 7)
```

`ab run` writes `./results/<utc>-<runid>/`:
- `trajectory.jsonl` — append-only event log per build spec §6
- `scores.json` — verdicts + total_score + pass flag
- `metadata.yaml` — model, tier, tier_hash, harness, timestamps
- `workdir/` — materialized sandbox (tier files + task fixtures + agent outputs)

---

## Architecture in one screen

```
┌──────────────┐   ab run   ┌─────────────┐  trajectory.jsonl  ┌──────────────┐
│   ab-cli     ├───────────►│  ab-harness ├───────────────────►│ results/<id> │
│ (task disc.) │            │ (runner +   │  scores.json       │              │
│              │   ab pub   │  sandbox +  │  metadata.yaml     │              │
│ publish_gate │◄───────────┤  scorers)   │                    │              │
└──────┬───────┘            └─────────────┘                    └──────┬───────┘
       │ git push                                                     │
       ▼                                                              │
┌──────────────┐  poll/15min  ┌─────────────────┐  re-score (replay)  │
│  GitHub      ├─────────────►│   ab-server     │◄────────────────────┘
│ results repo │              │ (fetcher +      │
└──────────────┘              │  rescoring +    │
                              │  leaderboard)   │
                              └────┬────────────┘
                                   │
                                   ▼
                              ┌─────────────────┐
                              │ ab-leaderboard  │  React SPA (5 pages):
                              │  Leaderboard ·  │   Leaderboard, Runs,
                              │  Run launcher · │   Tasks, Trends,
                              │  Tasks · Trends │   Settings (repos +
                              │  · Settings     │   account + privacy)
                              └─────────────────┘
```

**Friend-aggregation path** (ADR-007): each operator registers a public
results repo via `ab register` or Settings → Add repo. The server's
fetcher worker (`fetch_queue_poll_interval_sec`, default 30s) clones,
ingests, re-scores. Server never gets write access. Full walkthrough:
[`docs/friend-onboarding.md`](docs/friend-onboarding.md).

---

## ADRs in force

001 Inspect AI · 002 6-layer architecture · 003 single-user start (partially superseded by 005) · 004 web app · 005 modular monorepo · 006 open source Apache 2.0 · 007 GitHub OAuth + pull-based aggregation · 008 config tiers as first-class axis.

See vault `Projects/agent-benchmarks/decisions.md` for full text.

---

## Docs

- [Build spec](agent_benchmarks_build_spec.md) — authoritative source of what to build
- `docs/architecture.md`
- `docs/trajectory-protocol.md` — JSONL event contract (build spec §6)
- `docs/config-tiers.md` — T0/T1/T2/T3 + tier_hash
- `docs/trust-tiers.md` — self_reported / verified / official
- `docs/adding-a-task.md` — contributor guide
- `docs/adding-a-model-adapter.md` — runner contract
- `CLAUDE.md` — project-level guidance for Claude Code sessions

---

## Project status

| Phase | Scope | Status |
|---|---|---|
| Phase 0 | Monorepo scaffolding (P0.1–P0.12) | done — commit `92995f2` |
| Phase 1 M1 | Local run path (rows 1–6) | done — commit `37eefa6` |
| Phase 1 M2 | Publish + server (rows 7–10) | in progress |
| Phase 1 M3 | Frontend (rows 11–15) | claude-designer agent |
| Phase 2+ | Per build spec | not started |

Friends-first OSS (ADR-006); patches welcome from invited collaborators.
