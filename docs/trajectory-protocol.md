# Trajectory protocol

Every run produces a single append-only JSONL file at `./results/<utc-iso>-<run-id>/trajectory.jsonl`. One JSON object per line. This file is the contract between runners, scorers, the SDK, and the server.

## Event types

Each line has an `event` field. There are exactly four event types.

### `run_start`

Always the first line. Records what is about to run.

```json
{
  "event": "run_start",
  "run_id": "01HZX...",
  "task_id": "L0_001",
  "model": "claude-sonnet-4-5",
  "harness": "claude-code-cli@0.4.1",
  "tier": "T2",
  "tier_hash": "sha256:...",
  "dataset_version": "ab-datasets==0.4.0",
  "prompt_template_hash": "sha256:...",
  "started_at": "2026-05-21T12:00:00Z"
}
```

### `turn`

One per conversational turn. Indexed from 0, strictly monotonic.

```json
{
  "event": "turn",
  "idx": 1,
  "role": "assistant",
  "prompt_delta": "...",
  "tool_calls": [{"name": "create_vault_file", "args": {"path": "Projects/x/decisions.md", "content": "..."}}],
  "tool_returns": [{"ok": true, "detail": "created"}],
  "model_output": "<assistant message>",
  "vault_state_diff": {"created": ["Projects/x/decisions.md"], "modified": [], "deleted": []},
  "tokens_in": 2200,
  "tokens_out": 280,
  "latency_ms": 3120,
  "cost_usd": 0.0123
}
```

### `scorer`

One per scorer invocation, in the order declared by `Task.scorer_chain`. Appears after the final `turn`.

```json
{
  "event": "scorer",
  "scorer": "schema_validator",
  "kind": "deterministic",
  "pass": true,
  "score": 1.0,
  "detail": "all fields present and valid"
}
```

LLM-judge ensembles also include a `judges` array with the per-judge raw output:

```json
{
  "event": "scorer",
  "scorer": "hallucination_check",
  "kind": "llm_judge",
  "pass": true,
  "score": 0.92,
  "detail": "3-judge majority",
  "judges": [{"model": "...", "verdict": "...", "score": 0.95}, "..."]
}
```

### `run_end`

Always the last line. Records totals and final status.

```json
{
  "event": "run_end",
  "finished_at": "2026-05-21T12:00:14Z",
  "status": "completed",
  "totals": {
    "tokens_in": 3434,
    "tokens_out": 280,
    "latency_ms": 14000,
    "cost_usd": 0.0123,
    "score": 0.96
  }
}
```

`status` is one of `completed`, `timeout`, `unrunnable`, `error`.

## Invariants

Enforced by `ab_sdk.results.validate(path)`. CI rejects trajectories that violate these.

1. Exactly one `run_start` (first line) and exactly one `run_end` (last line).
2. `run_end.status` is in `{completed, timeout, unrunnable, error}`.
3. `turn.idx` starts at 0 and increases by exactly 1 each turn. No gaps, no duplicates.
4. `tool_calls` and `tool_returns` are arrays of equal length and aligned by index. Neither is null.
5. `vault_state_diff` is null on stateless turns, otherwise an object with `created`, `modified`, `deleted` arrays of repo-relative paths inside the sandbox vault root.
6. `scorer` events appear after the final `turn` and follow the order in `Task.scorer_chain`.
7. For any trajectory that will be `ab publish`-ed, a `privacy_check` scorer event must appear in the chain and must have `pass: true`.
8. Token counts, latency, and cost are per-turn (`turn.*`) and cumulative (`run_end.totals.*`). The cumulative values equal the per-turn sums within rounding tolerance for `cost_usd`.

## Re-runnability

Deterministic scorers (`deterministic`, `schema`, `exec`, `state_diff`, `privacy_check`) must be re-executable from the trajectory file alone. This is the property that lets the server re-score a submission and award the `verified` trust tier (LSN-007, ADR-007). LLM-judge scorers are recorded with full judge output so the server can audit but is not required to re-execute.

## Example: minimal valid trajectory

```jsonl
{"event":"run_start","run_id":"01HZX","task_id":"L0_001","model":"claude-sonnet-4-5","harness":"claude-code-cli@0.4.1","tier":"T0","tier_hash":"sha256:abc","dataset_version":"ab-datasets==0.4.0","prompt_template_hash":"sha256:def","started_at":"2026-05-21T12:00:00Z"}
{"event":"turn","idx":0,"role":"user","prompt_delta":"List the files.","tool_calls":[],"tool_returns":[],"model_output":"","vault_state_diff":null,"tokens_in":42,"tokens_out":0,"latency_ms":0,"cost_usd":0.0}
{"event":"turn","idx":1,"role":"assistant","prompt_delta":"","tool_calls":[{"name":"bash","args":{"cmd":"ls"}}],"tool_returns":[{"ok":true,"detail":"a.py\nb.py"}],"model_output":"Found two files.","vault_state_diff":null,"tokens_in":120,"tokens_out":18,"latency_ms":410,"cost_usd":0.0004}
{"event":"scorer","scorer":"exec_check","kind":"deterministic","pass":true,"score":1.0,"detail":"ls succeeded"}
{"event":"scorer","scorer":"privacy_check","kind":"deterministic","pass":true,"score":1.0,"detail":"no matches"}
{"event":"run_end","finished_at":"2026-05-21T12:00:01Z","status":"completed","totals":{"tokens_in":162,"tokens_out":18,"latency_ms":410,"cost_usd":0.0004,"score":1.0}}
```
