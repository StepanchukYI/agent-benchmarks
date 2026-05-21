# Adding a task

A task is a YAML file under `packages/ab-datasets/ab_datasets/L<layer>_<bucket>/`. The schema is `ab_datasets.schemas.Task`. This guide walks through the steps.

## 1. Pick a layer and suite

Layers (per ADR-002):

- L0 foundation — file ops, schema validation, exec
- L1 memory — vault writes, decisions, lessons, hub updates
- L2 skills — single-skill correctness
- L3 domains — obsidian, lantern, backstage, gitnexus, graphify
- L4 composite — multi-skill, multi-tool, multi-turn
- L5 evolved — auto-evolved configs and tasks

A suite is a coherent subgroup within a layer (e.g., `memory-write`, `decision-schema`, `gitnexus-impact-check`).

## 2. Create the YAML file

Path: `packages/ab-datasets/ab_datasets/L<n>_<bucket>/<task-id>.yaml`. Filename = `<id>-<slug>.yaml`. Task ids are `L<n>_NNN`.

Minimum required fields:

```yaml
id: L1_001
layer: L1
suite: memory-write
title: "Write decision with full frontmatter schema"
description: |
  One-paragraph summary of the user-facing prompt the agent receives.
config:
  required_tier: T2
  recommended_tier: T2
  also_run_on: [T0, T1]
  requires:
    skills: [memory:memory-write]
    mcps: [obsidian-memory]
    vault_state: { has_decisions_md: true, has_hub_md: true }
fixture_ref: fixtures/vault_snapshots/T2_seed_small.tar.gz
scorer_chain:
  - { name: schema_validator,    kind: deterministic, config: { required_fields: [importance, valid_until, sub_type] } }
  - { name: hallucination_check, kind: llm_judge,     config: { ensemble: 3 } }
  - { name: privacy_check,       kind: deterministic, config: {} }
acceptance_criteria:
  - "decisions.md contains a new entry with the user-provided context."
  - "importance in [1,5]; valid_until parses as ongoing or YYYY-MM-DD."
weights: { correctness: 0.5, memory_specific: 0.4, latency: 0.05, context_efficiency: 0.05 }
difficulty: medium
visibility: public
trust_tier_ceiling: verified
tags: [decision, schema, memory-write]
```

Required fields enforced by the Pydantic model: `id`, `layer`, `suite`, `title`, `description`, `fixture_ref`, `scorer_chain`, `config.required_tier`, `acceptance_criteria`, `weights`, `difficulty`, `visibility`, `trust_tier_ceiling`.

## 3. Add fixtures

Fixtures live under `packages/ab-datasets/fixtures/`. **`fixture_ref`
is always prefixed with `fixtures/`** and resolves relative to
`packages/ab-datasets/`. `tests/test_l0_fixtures_resolve.py` enforces
this for L0; the same convention applies to L1+.

Canonical fixture roots:

- `fixtures/vault_snapshots/` — anonymized `.tar.gz` archives.
- `fixtures/repos/` — test repos for L0 file-ops + L4 bug-fix tasks
  (under `fixtures/repos/L0_smoke/L0_NNN/` for L0).
- `fixtures/mcp_mocks/` — fake MCP server definitions for verifiable
  L3 tasks.
- `fixtures/config_tiers/T{0..3}_*/manifest.yaml` — already shipped;
  reference the tier id from `config.required_tier`, not from
  `fixture_ref`.

Every fixture is listed in `packages/ab-datasets/fixtures/manifest.yaml`
with SHA256, size, and visibility. Regenerate after any fixture change.

Anonymize first: scrub real names, real paths, real API keys. Run
`python scripts/privacy_scan.py` against the fixture before
committing. Zero hits required.

## 4. Wire the scorer chain

Every chain must contain at least one deterministic scorer (LSN-004 — LLM-judge alone is not a scorer). Available scorer kinds: `deterministic`, `llm_judge`, `state_diff`, `schema`, `exec`, `privacy_check`. Add `privacy_check` to any chain whose trajectory might be published.

If you want `trust_tier_ceiling: verified`, every deterministic scorer in the chain must be re-runnable from `trajectory.jsonl` alone — no external state, no live API calls. Otherwise set the ceiling to `self_reported`.

### Scorer-per-pillar (L0 convention)

L0 tasks ship one explicit scorer per scoring pillar so weighted
totals correspond 1:1 to scorer verdicts. After your task-specific
correctness scorer(s) and `privacy_check`, append the standard three:

```yaml
  - name: tool_skill
    kind: deterministic
    config: { max_tool_calls: <int>, pass_threshold: 0.5 }
  - name: context_efficiency
    kind: deterministic
    config: { target_tokens: <int>, max_tokens: <int>, pass_threshold: 0.3 }
  - name: latency_cost
    kind: deterministic
    config: { target_ms: <int>, max_ms: <int>, pass_threshold: 0.3 }
```

Pick budgets per task difficulty (smoke tasks use 30 tool calls,
20000 tokens, 180000 ms; tighter probes use 1-5 tool calls, 3000-8000
tokens, 60000 ms). Add `memory_specific` as a weight key for L1+
tasks; the corresponding scorer is task-specific (state_diff or
schema_validator over the vault file).

The `weights` map MUST sum to exactly 1.0; this is enforced by
`tests/test_pilot_tasks.py::test_task_weights_sum_to_one`.

## 5. Test locally

```bash
uv run ab task validate packages/ab-datasets/ab_datasets/L1_memory/L1_001-write-decision.yaml
uv run ab task dry-run L1_001 --runner mock
uv run ab run --suite memory-write --model claude-sonnet --tier T2
```

`dry-run` uses a mock runner that returns canned outputs so you can iterate on scorers without burning tokens.

## 6. Repo-wide invariants your task must satisfy

Before opening a PR your new task must pass these tests in
`packages/ab-datasets/tests/`:

- `test_pilot_tasks.py` (runs against every YAML in `L*/`):
  - validates against the Pydantic schema (extra fields rejected),
  - weights sum to exactly 1.0,
  - at least one deterministic-class scorer in the chain (LSN-004),
  - `privacy_check` scorer present (LSN-006),
  - `trust_tier_ceiling` within the per-layer ceiling (`docs/trust-tiers.md`),
  - ≥1 acceptance_criteria,
  - `required_tier`/`recommended_tier`/`also_run_on` are canonical T0..T3,
  - L0 tasks have no `llm_judge` scorer (re-runnability requirement).
- `test_l0_fixtures_resolve.py` (L0-only): every declared `fixture_ref` exists on disk under `packages/ab-datasets/`.
- `test_l0_taxonomy.py` (L0-only): suite coverage, mirror pairs, tier-delta canary all present.

## 7. Open a PR

- Use the `New task` issue template to track the proposal.
- Run `ruff check`, `pytest -q`, and `python scripts/privacy_scan.py` locally.
- Regenerate schemas if you touched any Pydantic model: `make schema-export`, commit the diff under `docs/schemas/`.
