---
name: New task
about: Propose a new benchmark task
title: "[task] "
labels: ["task", "needs-triage"]
assignees: []
---

## Layer

Which layer does this task belong to?

- [ ] L0 — foundation (file ops, schema, exec)
- [ ] L1 — memory
- [ ] L2 — skills
- [ ] L3 — domains (obsidian, lantern, backstage, gitnexus, graphify)
- [ ] L4 — composite (multi-skill, multi-tool)
- [ ] L5 — evolved

## Suite

Existing suite this fits into, or proposed new suite name.

## Required tier

Minimum `required_tier` (T0 vanilla / T1 minimal / T2 personal / T3 full).
Also list any tiers you want it to run on via `also_run_on`.

## Scorer chain ideas

Sketch the ordered scorer chain. At least one must be deterministic (LSN-004).

- [ ] deterministic: <name + what it checks>
- [ ] llm_judge: <name + criteria> (optional, only paired with deterministic)
- [ ] state_diff: <files / vault paths it diffs>
- [ ] schema: <Pydantic model or JSON Schema>
- [ ] exec: <command, expected exit code>
- [ ] privacy_check: included if trajectory will be published

## Acceptance criteria

Plain-English statements that an evaluator can check by reading the trajectory + diffs.

- [ ] <criterion 1>
- [ ] <criterion 2>

## Fixtures needed

- [ ] vault snapshot: <name + approx size>
- [ ] repo fixture: <name + language>
- [ ] MCP mock: <which servers, what they should return>

## Trust tier ceiling

Maximum trust tier this task can earn (`self_reported` / `verified` / `official`).
Mark `verified` only if deterministic scorers in the chain can be re-run from `trajectory.jsonl` alone.
