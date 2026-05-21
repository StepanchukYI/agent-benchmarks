# Roadmap — `agent-benchmarks`

> Status snapshot: 2026-05-21
> Phase boundaries follow `vault://Projects/agent-benchmarks/hub.md`.
> When this file contradicts the hub, the hub wins.

---

## Phase status overview

| Phase | What ships | Status |
|---|---|---|
| **Phase 0** Scaffold | Six-package monorepo, schemas, fixtures, CI, privacy gate | ✅ Done |
| **Phase 1 M1** Local run | `ab run` end-to-end, 5 deterministic scorers, sandbox materialize | ✅ Done |
| **Phase 1 M2** Server + publish | OAuth, register/publish, fetcher worker, re-scoring, `/leaderboard` endpoint | ✅ Done |
| **Phase 1 M3** Frontend | React SPA with 5 surfaces, settings tabs, hooks wired | ✅ Done (subtab gaps closed 2026-05-21) |
| **Phase 2 Runners** | claude-code / codex-cli / gemini-cli / opencode / pi-agent / anthropic-compat / openai-compat / local / mock | ✅ Done |
| **Phase 2 Wizard + scripts** | `ab wizard` interactive picker, `run_quick.sh`, `run_matrix.sh`, `serve_local.sh` | ✅ Done |
| **Phase 2 Friend onboarding** | GitHub device-flow OAuth → register repo → publish → server pulls + re-scores | ✅ Done |
| **Phase 3 Task corpus** | 100+ L0 tasks, 25+ L1, full L2/L3a/L3b/L3c/L4 sets | 🚧 In progress (84 L0 live, others in pilot) |
| **Phase 4 L5 evolved** | Auto-task generation from execution traces | ⏸ Spec'd |
| **Phase 5 Public launch** | Public web, governance ADR, anti-abuse spec | ⏸ After Phase 3 |
| **Phase 6+ Long-tail** | Multi-tenant scaling, multi-repo split, HF Hub publication | ⏸ Trigger-based |

---

## Phase 0 — Scaffold (✅ done)

P0.1 — `pyproject.toml` uv workspace + `pnpm-workspace.yaml`
P0.2 — Six package skeletons with `__init__.py` + minimal `pyproject.toml`
P0.3 — Pydantic schemas for Task / Trajectory / Tier / ScorerVerdict / Submission / AgentConfig
P0.4 — JSON Schema export via `make schema-export` → `docs/schemas/`
P0.5 — CI green (ruff, pytest, schema diff, privacy scan, FE typecheck)
P0.6–0.12 — Per-package boilerplate, tests-e2e harness, infra/docker-compose, docs scaffolding

Exit criterion: `uv sync && uv run pytest && pnpm typecheck` clean on fresh clone.

---

## Phase 1 — Local + Server (✅ done)

### M1 — Local run path
- M1.1 — 5 L0 task YAMLs + fixtures + validators
- M1.2 — `ClaudeCodeRunner` real impl + trajectory finalization
- M1.3 — 5 deterministic scorers (file_diff, schema, exec, state_diff, privacy_check)
- M1.4 — Docker sandbox tier materialize (T0/T2)
- M1.5 — `ab-sdk` write/read round-trip + privacy gate
- M1.6 — `ab run` end-to-end

### M2 — Publish + server
- M2.7 — `ab register` GitHub device-flow + `ab publish` to contributor repo
- M2.8 — Server CRUD + fetcher worker polling registered repos
- M2.9 — Re-scoring engine + `verified` trust tier resolution
- M2.10 — `/leaderboard` endpoint with filter axes

### M3 — Frontend
- Integrated designer's UI (`packages/ab-leaderboard`)
- Wire UI A/B/C: backend reshape, hooks consume real endpoints, e2e tests
- P0 cleanup: drop unused API runners, normalize TurnEvent adapter, empty-state UI, OAuth UI wiring, getting-started doc
- **Subtab wire-up (2026-05-21)**: Leaderboard pillar tabs, Runs status tabs, Trends 5 tabs, TrajectoryViewer Tasks/Trajectories tabs, Settings Tokens UI, Account visibility toggles. Closes ~60% of placeholder SubNav entries.

---

## Phase 2 — Runners + friend onboarding (✅ done)

- P1.7 `CodexCLIRunner`
- P1.8 `OpenCodeRunner`
- P1.9 `GeminiCLIRunner`
- `pi-agent` runner (pi.dev)
- `anthropic-compat` runner with vendor routing (zhipu / minimax / moonshot / deepseek via `ANTHROPIC_BASE_URL`)
- `openai-compat` runner for OpenAI + local OpenAI-compatible servers
- `local` runner for ollama / lm-studio
- `mock` runner for CI tests
- `ab wizard` interactive picker
- `scripts/{run_quick,run_matrix,serve_local}.sh`
- Friend onboarding doc (`docs/friend-onboarding.md`)
- Server endpoints: `/me`, `/account/repos`, `/account/privacy-rules`, `/account/tokens`, `PATCH /me/visibility`

Stubs remaining for: `hermes-agent` (Nous Research), `nanobot` (HKUDS), `cursor` (no public CLI). Tracked, not blocking.

### Honest isolation (LSN added 2026-05-21)
- `IsolatedEnv` whitelist for all 5 host runners
- Opt-in `AB_CLAUDE_HIDE_USER_CONFIG=1` for honest CLAUDE.md isolation
- 25-test pin suite (`test_runners_isolation.py`)

---

## Phase 3 — Task corpus (🚧 in progress)

### Track A (platform) — already at done state for Phase 1-2.
Open issues for Track A:
- TrajectoryViewer Cost/Diff/Export endpoints + UI (deferred, separate task)
- Weights normalization audit: some L0 YAMLs reference pillars whose scorer slot is empty (authoring inconsistency, not wiring — separate pass)
- Settings "Other" tab — undefined scope

### Track B (task corpus) — ongoing
L0 status:
- 84 task YAMLs live (file-ops, NIAH, code-context, output-constraints, citation honesty, skill router, reasoning)
- 79 named scorers wired into the assertion-chain dispatcher
- Track B authoring continues toward 100+

L1 status:
- Pilot task authored (L1_001 — memory write schema)
- Backlog: 25+ tasks across write schema correctness, hierarchical retrieval, dreaming consolidation, contradiction detection, temporal validity

L2 status:
- Pilot task authored (L2_001 — skill router under MCP load)
- Backlog: per-runner skill-routing tasks

L3 status:
- L3a (Obsidian): pilot task authored, backlog drafted
- L3b (Lantern): backlog drafted
- L3c (Backstage): backlog drafted
- L3d (GitNexus / Graphify): backlog drafted
- L3e+ (Letta / Mem0 / Cloudflare Agent Memory / ReMe / Zep / supermemory): open contribution path, adapter contract spec'd

L4 status:
- 1 pilot composite task authored
- Backlog: 2-5 more cross-system tasks

Exit criterion for Phase 3:
- 100+ L0
- 25+ L1
- 1+ L2 per shipped runner
- 5+ L3 adapters live with L1 coverage
- 3+ L4 composite tasks

---

## Phase 4 — L5 evolved (⏸ spec'd)

Karpathy-style auto-task generation from execution traces. Plan:

1. Mine completed runs for "interesting" decision points (large divergence between models, novel tool sequences, contradiction-flagged turns)
2. Auto-generate variants via LLM (paired with deterministic regression test)
3. Human-review pass (small batch, manual approve / reject)
4. Approved batch lands as new L5 task subdirectory
5. `ab evolve` CLI command drives the loop

Open: scorer for LLM-generated tasks. Decision: pair LLM-judge with deterministic regression test (LSN-004 — never LLM-judge alone). Trust tier ceiling: `verified` for exec/schema scorer paths; `self_reported` for LLM-judge paths until human review.

---

## Phase 5 — Public launch (⏸ deferred)

Pre-launch requirements:
- 3+ external contributors with `verified` trust tier
- Governance ADR (BDFL + lazy consensus until N ≥ 5 contributors, then community RFC process)
- Anti-abuse spec (OQ15 — rate limit / CAPTCHA / auth-only on anonymous submissions)
- Server hosting decision (OQ17 — Fly.io vs Railway vs self-hosted homelab)
- Public OAuth app (currently personal-only)
- License confirm (Apache 2.0 per ADR-006)
- Public web with documented onboarding path

---

## Phase 6+ — Long-tail (⏸ trigger-based)

Multi-repo split triggers (per ADR-005):
- HF Hub publication → extract `ab-datasets`
- First external `verified` submission → extract `ab-server` + `ab-sdk`
- Public-domain leaderboard → extract `ab-leaderboard`

Multi-tenant scaling (OQ — defer until N ≥ 20 friends):
- Postgres tenancy with row-level security
- Per-contributor re-scoring queue + quota
- Webhook flow (currently 15-min poll per ADR-007 / OQ22)

---

## Active open questions blocking next phases

| # | Question | Default | Blocks |
|---|---|---|---|
| OQ13 | Trust-tier policy details for L3 private / L4 composite | Per LSN-005 layer ceilings | Phase 5 public launch |
| OQ14 | Anonymized fixtures for L3a/L4 | Yes, separate two-tier dataset package | Phase 5 |
| OQ15 | Anti-abuse on anonymous submissions | Defer until first inbound | Phase 5 |
| OQ17 | Server hosting | Fly.io or Railway | Phase 5 |
| OQ18 | GitHub org or personal | Personal v1 | Phase 5 |
| OQ20 | Governance once 3+ contributors | BDFL + lazy consensus | Phase 5 |
| OQ24 | Re-scoring compute budget | Unlimited until N ≥ 20 | Phase 6 |
| OQ29 | Repo-declared tier vs per-result tier | Per-result; metadata.yaml declares it | Phase 3 (resolved) |

---

## Recent commits (since 2026-05-21)

| SHA | Title |
|---|---|
| `ec02bd0` | feat(scorers): close 49 missing Track-B names + add workdir-file assertions |
| `641a446` | feat(scorers,datasets): scorer dispatch fix + L0 batch (52 new yamls) |
| `15b5c45` | feat(server): pillar filter + visibility toggles + API tokens |
| `e3e86c7` | feat(leaderboard): subtab wire-up + Settings Tokens UI + visibility toggles |

Full log: `git log --oneline -20`.
