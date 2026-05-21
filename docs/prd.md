# Product Requirements — `agent-benchmarks`

> Status: v1.1 (2026-05-21)
> Authoritative ADRs: `vault://Projects/agent-benchmarks/decisions.md`

---

## 1. Problem statement

Public benchmarks for coding agents measure single-turn correctness against curated test suites. They don't measure:

1. **Memory write-in-flight quality** — does the agent record the right facts in the right place when working on a task? (LSN-001)
2. **Skill / MCP triggering** — does the agent pick the correct tool from a library of 30+, or hallucinate a fake one? (LSN-002)
3. **Cross-system composite work** — does the agent route correctly across an Obsidian vault + Lantern + Backstage + GitNexus stack?
4. **Initial config sensitivity** — how much does the answer depend on the operator's CLAUDE.md / skills / vault snapshot? (LSN-008)
5. **Contamination resistance** — do model answers drop on freshly authored tasks vs. training-set echo? (LSN-003)

Existing benches optimize the agent's single-shot output. We optimize the **full daily-use stack**: model + memory + skills + MCP routing, with the operator's actual context loaded.

---

## 2. Target users

| User | What they get |
|---|---|
| **Model provider** | Honest per-model scores across 7 layers with replay-verifiable trajectories. Compare GPT-5 vs Sonnet vs GLM on the same task without rerunning. |
| **Tooling author** (memory backend, MCP server, skill plugin author) | A reusable L3 adapter contract — implement the adapter once, inherit L1 memory + L2 skill coverage for free. |
| **Daily-use operator** (the maintainer + invited friends) | Track regression on personal stack. Catch the day a model update breaks my memory-write recall, my skill router, my MCP retry logic. |
| **Researcher** | Public dataset (`ab-datasets`) + reproducible runs + cross-system L4 composite tasks not available in any other bench. |

Friends-first invite-only initially (ADR-006, OQ19). Public after first 3 external contributors + governance ADR.

---

## 3. Scope — 7 layers

L0 ships shipped. L1–L5 progressively land.

| Layer | Theme | Status | Authoring track |
|---|---|---|---|
| L0 Foundation | File ops, NIAH, tool routing, output constraints, citation honesty, skill router, reasoning | **Shipped** (84 tasks live) | Track B |
| L1 Memory schema | Write schema correctness, hierarchical retrieval, dreaming consolidation, contradiction detection, temporal validity | Pilot task authored | Track B |
| L2 Skill router | Plugin / MCP triggering vs hallucination across 30+ libraries | Pilot task authored | Track B |
| L3a Memory backend (Obsidian) | Personal vault PARA + MemPalace + Karpathy + rooms | Pilot task authored | Track B |
| L3b Memory backend (Lantern) | Work-context MCP | Backlog | Track B |
| L3c Code-context (Backstage) | Spotify developer portal | Backlog | Track B |
| L3d Code-graph (GitNexus / Graphify) | Browser-side + multi-language KGs | Backlog | Track B |
| L3e+ More adapters | Letta / Mem0 / Cloudflare Agent Memory / ReMe / Zep / supermemory | Open contribution path | Community |
| L4 Composite | Multi-system tasks (memory + skills + code-graph in one job) | Pilot task authored | Track B |
| L5 Evolved | Auto-generated tasks from execution traces. Karpathy-style. | Spec'd | Track A automation |

Each layer has a recommended config tier (T0/T1/T2/T3) and `also_run_on` for cross-tier comparison.

---

## 4. Non-goals (explicit)

- **Not a coding-skill bench.** SWE-bench, HumanEval, LiveCodeBench cover that. We measure the full stack, not the model's coding chops.
- **Not a foundation-model leaderboard.** We measure model + tool + memory + skill router in combination. A model's score depends on the operator's setup.
- **Not a public anonymous-submission service v1.** Friends-first. Anti-abuse spec deferred (OQ15).
- **Not a managed cloud service.** Self-hostable. The maintainer runs one public instance; friends can run their own.

---

## 5. Data flow

```
Operator runs `ab run` locally
  → IsolatedEnv subprocess (Max-keychain auth, optional config-hide)
  → trajectory.jsonl + scores.json + metadata.yaml written to results/
  → `ab publish` pushes to operator's GitHub contributor repo
  → server fetcher polls (15min) and discovers new commit
  → re-score worker validates trajectory schema, re-runs deterministic scorers
  → trust_tier resolved (self_reported vs verified)
  → leaderboard row materialized
```

See `architecture.md` for the detailed flow diagram.

---

## 6. Quality requirements

### Re-runnability (LSN-007)
Every deterministic scorer must expose `.run(workdir, task)` AND `.replay(traj_path, task)`. If a scorer can only run live, it returns `replay_unsupported` verdict and the row caps at `self_reported`. No exceptions — this is what makes third-party trajectories trustworthy.

### Privacy (LSN-006, three layers)
1. Pre-commit hook in contributor repos
2. `privacy_check` scorer inside every publishable trajectory
3. `privacy-scan` CI workflow at the repo level

Patterns in `privacy-patterns.yaml`. Zero hits on every public commit.

### Trajectory protocol
Append-only JSONL. Exactly one `run_start` (first) + one `run_end` (last). Strictly monotonic `turn.idx` from 0. Scorers strictly after the last turn. Tool calls / returns are non-null arrays.

### Config tiers as first-class axis (ADR-008)
Every task declares `required_tier` and optional `also_run_on`. The leaderboard's primary axis is (model × effort × tier). Comparing T0 vs T2 on the same task is the headline value prop.

### LLM-judge never alone (LSN-004)
Always pair an LLM-judge scorer with at least one deterministic scorer in a chain. Karpathy-style auto-research belongs in task generation (L5), not primary judging.

---

## 7. Success criteria (v1 ship)

- 100+ L0 tasks (current: 84) covering 7 themes
- 25+ L1 tasks across 5 memory operations
- 1+ L2 task per shipped runner (claude-code / codex-cli / gemini-cli / opencode / pi-agent / anthropic-compat / openai-compat)
- 5+ L3 adapters (memory + code-graph) with shared L1 coverage
- 3 L4 composite tasks
- 1 L5 auto-evolved batch (≥10 tasks generated from real traces)
- 5+ external contributors with `verified` trust tier on the leaderboard
- Server self-hostable from one `docker compose up`
- Privacy boundary holds: zero `privacy_check` hits across all public commits
- All scorer chains in shipped tasks are replay-capable OR the row caps correctly

---

## 8. Out-of-band requirements

### Honest isolation
Benchmark runs must NOT leak operator-side context (CLAUDE.md, skills, vault) into the subprocess. `IsolatedEnv` whitelist + opt-in `AB_CLAUDE_HIDE_USER_CONFIG=1` for honest isolation. Verified by `test_runners_isolation.py` (25 tests).

### Max-subscription friendliness
The `claude-code` runner must work with macOS Keychain auth (no API key). Operators with Max subscriptions should pay zero per-token cost to run the benchmark.

### Vendor routing (Chinese providers)
The `anthropic-compat` runner accepts `--vendor zhipu|minimax|moonshot|deepseek` + `--env ANTHROPIC_AUTH_TOKEN=$KEY` to route to vendor-specific base URLs without forking the runner.

### Server cost discipline
Re-scoring is unlimited until N ≥ 20 submissions / week (OQ24). Above that, queue + rate-limit per contributor repo.

---

## 9. Authoritative references

| What | Where |
|---|---|
| Active ADRs (001–012) | `vault://Projects/agent-benchmarks/decisions.md` |
| Lessons (001–012) | `vault://Projects/agent-benchmarks/lessons.md` |
| Architecture | `docs/architecture.md` |
| Roadmap | `docs/roadmap.md` |
| Trajectory protocol | `docs/trajectory-protocol.md` |
| Trust tiers | `docs/trust-tiers.md` |
| Config tiers | `docs/config-tiers.md` |
| Privacy patterns | `docs/privacy-patterns.yaml` |
| Friend onboarding | `docs/friend-onboarding.md` |
| Getting started | `docs/getting-started.md` |
| L3 adapter landscape | `docs/L3_adapter_landscape.md` |
| Research bench survey | `docs/research-bench-survey.md` |
