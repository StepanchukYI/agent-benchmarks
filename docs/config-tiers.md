# Config tiers (ADR-008 in plain English)

A "tier" is a reproducible bundle of operator configuration — CLAUDE.md, skills, MCP configs, and vault state — that the sandbox materializes before a task runs. Tiers are a first-class axis on the leaderboard: the same model on the same task at T0 and T2 yields two separate scores, and the delta is what teaches us how much config matters.

There are four initial tiers. Tier ids are stable across releases.

## T0 — Vanilla

The bare model, no operator configuration. No CLAUDE.md, no skills, no MCPs, empty vault. Whatever the harness ships out of the box, nothing more.

Use case: control. Establishes the floor for every task. Any score above zero on an L1+ task tells us config matters for this capability.

## T1 — Minimal

A small, public CLAUDE.md only. No skills, no MCPs, no vault. The CLAUDE.md is a generic "you are a careful engineer" prompt with a few coding ground rules — short enough to fit on one screen.

Use case: isolate the effect of system-prompt scaffolding alone, before any tools or memory.

## T2 — Personal

A realistic operator config without the maintainer's identity.

- CLAUDE.md: anonymized version of the maintainer's global CLAUDE.md (the "six laws", quality rules, anti-sycophancy, research methodology, intellectual integrity).
- Skills: `memory:memory-session`, `memory:memory-write`, `memory:memory-ops`, plus a small productivity bundle (task management, basic web).
- MCPs: `obsidian-memory` (mocked in CI), `scheduled-tasks`. Two servers, both deterministic in mock mode.
- Vault: small seed snapshot — hub + decisions + lessons schema, no real project content.

Use case: the most common realistic baseline. Most L1–L3 tasks are anchored at T2.

## T3 — Full

Everything the maintainer actually runs locally, anonymized.

- CLAUDE.md and CLAUDE.local.md: anonymized but otherwise complete.
- Skills: the full anonymized skill library (memory, gitnexus, lantern, backstage, frontend-design, plugin-dev, etc.).
- MCPs: full set, all mocked in CI.
- Vault: medium-sized anonymized snapshot.

Use case: ceiling. Tells us how much further a fully kitted operator config carries the same model on the same task.

## Cross-tier runs

```bash
ab run --suite L1 --model claude-sonnet --tiers T0,T2,T3
```

The harness produces three trajectories per task. The server computes `tier_delta(T2 - T0)` and `tier_delta(T3 - T0)` automatically; the leaderboard exposes them as separate columns.

## How `tier_hash` is computed

A tier's content hash is a deterministic rollup of its parts:

```
total_sha256 = sha256(
  manifest.yaml          # tier id, description, lists of skill ids and MCP ids
  || claude_md_sha256
  || claude_local_md_sha256
  || skill_id_1 || skill_sha256_1
  || skill_id_2 || skill_sha256_2
  || ...
  || mcp_id_1 || mcp_config_sha256_1
  || ...
  || vault_snapshot_sha256
)
```

The order is deterministic (lexicographic by id within each section). Skills and MCPs included via wildcards expand at materialization time and contribute their concrete ids and content hashes.

`tier_hash` is recorded in every trajectory's `run_start` event. The server uses it to detect whether two submissions ran against the same tier or against subtly different ones. Two trajectories with different `tier_hash` values are never aggregated as if they were the same configuration.

## Trust-tier interaction

A tier's manifest, including content hashes for every skill, MCP config, and snapshot, must be reproducible from public artifacts for a trajectory to qualify for `verified` trust tier. T0, T1, T2 are designed to satisfy this. T3 may include components that are not yet public — when that happens, tasks running on T3 fall back to `self_reported` until the components are open-sourced.
