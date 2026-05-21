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
fixture_ref: vault_snapshots/T2_seed_small.tar.gz
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

Fixtures live under `packages/ab-datasets/fixtures/`:

- `vault_snapshots/` — anonymized `.tar.gz` archives.
- `repos/` — test repos for L0 file-ops + L4 bug-fix tasks.
- `mcp_mocks/` — fake MCP server definitions for verifiable L3 tasks.
- `config_tiers/T{0..3}/manifest.yaml` — already shipped; reference from `config.required_tier`.

Every fixture has a sha256 recorded in its `Fixture` entry. Use `ab fixture add` (CLI helper, P1) or compute manually with `shasum -a 256`.

Anonymize first: scrub real names, real paths, real API keys. Run `python scripts/privacy_scan.py` against the fixture before committing.

## 4. Wire the scorer chain

Every chain must contain at least one deterministic scorer (LSN-004 — LLM-judge alone is not a scorer). Available scorer kinds: `deterministic`, `llm_judge`, `state_diff`, `schema`, `exec`, `privacy_check`. Add `privacy_check` to any chain whose trajectory might be published.

If you want `trust_tier_ceiling: verified`, every deterministic scorer in the chain must be re-runnable from `trajectory.jsonl` alone — no external state, no live API calls. Otherwise set the ceiling to `self_reported`.

## 5. Test locally

```bash
uv run ab task validate packages/ab-datasets/ab_datasets/L1_memory/L1_001-write-decision.yaml
uv run ab task dry-run L1_001 --runner mock
uv run ab run --suite memory-write --model claude-sonnet --tier T2
```

`dry-run` uses a mock runner that returns canned outputs so you can iterate on scorers without burning tokens.

## 6. Open a PR

- Use the `New task` issue template to track the proposal.
- Run `ruff check`, `pytest -q`, and `python scripts/privacy_scan.py` locally.
- Regenerate schemas if you touched any Pydantic model: `make schema-export`, commit the diff under `docs/schemas/`.
