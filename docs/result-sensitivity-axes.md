# Result-sensitivity axes

The leaderboard already tracks four primary axes: **model × runner ×
tier × task**. This document enumerates the **secondary axes** that
also move scores but are not currently captured as first-class
columns in `Submission`. Without recording them, cross-submission
comparisons can be misleading.

This is a Track-B-authored inventory of effects. Whether each axis
should become a first-class submission field, a per-task tag, or
stay informational is a Track-A decision.

## Inventory

### 1. Reasoning / thinking budget

| Effect | Where it bites |
|---|---|
| Same model with `thinking=off` vs `thinking=high` differs by 20–40 % on multi-hop, contradiction-resolution, exact-count, and adversarial tasks. | L0_103, L0_201, L0_202, L0_308, L0_402, L0_503, L0_602, L0_605, L0_607 |

**Action**: tag affected tasks `reasoning-sensitive`. Track A
should add `agent_config.reasoning_effort` and
`agent_config.thinking_budget_tokens` to `Submission`.

### 2. Sampling parameters (temperature, top_p, top_k)

| Effect | Where it bites |
|---|---|
| `temperature ≥ 0.5` makes byte-exact assertions stochastically flaky. `temperature=0` reduces but doesn't eliminate (some runners floor at 0.1). | All byte-exact L0 tasks (L0_001, 002, 006, 007, 010, 401, 402, 403, 502, 608). |

**Action**: tag those tasks `byte-exact-output`. Recommend
`temperature: 0` in `docs/result-sensitivity-axes.md`. Track A
should record sampling params in trajectory `run_start`.

### 3. Output max-tokens / truncation

| Effect | Where it bites |
|---|---|
| Long-context tasks where the model writes a long chain-of-thought before answering may exceed `max_output_tokens` and get truncated mid-answer. | L0_103, 201, 202, 503 (reasoning-heavy with structured final answer). |

**Action**: tasks already declare generous `context_efficiency.max_tokens`.
Track A trajectory should record `output_tokens_used` and
`output_truncated: bool`.

### 4. Model snapshot / knowledge cutoff

| Effect | Where it bites |
|---|---|
| Factual recall tasks return different answers when the model's training data differs. | L0_603 (Eiffel Tower completion year = 1889 — stable across snapshots) and L0_608 (Au — stable). Future L0 factual-recall tasks should be **stability-tested** before adding. |

**Action**: tag `factual-recall`. Only ship factual probes whose
answer is fixed pre-1900 OR is part of universal chemistry/physics
constants. Avoid current-events probes that drift with cutoff.

### 5. Output normalization (trim, wrap, markdown)

| Effect | Where it bites |
|---|---|
| Some runners strip trailing whitespace; some wrap output in markdown fence; some auto-prepend "Sure, here you go:" prose. | L0_001, 002, 006, 007, 010, 401, 402, 403, 502, 608. |

**Action**: tag `output-normalization-sensitive`. Scorers should
configure `trim_trailing_whitespace`, `strip_markdown_fence`
options explicitly per task (some already do; audit pass needed).

### 6. Tokenizer / "word" definition

| Effect | Where it bites |
|---|---|
| L0_402 requires "exactly 14 whitespace-separated tokens". Different models tokenize differently internally but **whitespace-tokenization** is well-defined for scoring. Hyphenated compounds and possessives can still surprise. | L0_402 only (single such task in L0). |

**Action**: tag `tokenizer-sensitive` if a task scores by token
count. L0_402 explicitly says "whitespace tokenizer"; this is
unambiguous for scoring even if models count differently
internally.

### 7. Context window size

| Effect | Where it bites |
|---|---|
| Haystacks are 12–42 KB (≈ 3k–11k tokens). Models with ≤8k context will fail not for capability reasons but for window-exhaustion. | L0_101, 102, 103, 201, 202. |

**Action**: tag `context-window-sensitive`. Submission should
include `model_context_window_tokens` so the leaderboard can
warn before showing meaningless results.

### 8. Runner-specific primitives (skill dispatch, MCP)

| Effect | Where it bites |
|---|---|
| L0_605 / L0_606 assume the runner emits `skill_invocation` events. Some runners (codex-cli, raw OpenAI API) do not have this primitive at all and would trivially pass L0_605 (zero invocations always) and trivially fail L0_606 (cannot invoke). | L0_605, L0_606 (mirror pair). Future L2 layer is entirely skill-routing. |

**Action**: tag `runner-skill-dispatch`. Tasks that depend on
runner-specific primitives should be **skipped, not failed**, when
the runner does not support that primitive — the leaderboard
should show `n/a` rather than 0.

### 9. Prompt language

| Effect | Where it bites |
|---|---|
| Some L0 prompts are Russian (L0_605, L0_606, L0_201 chain-of-name). Multilingual models handle them; English-only models may fail. | L0_605, L0_606. |

**Action**: tag `language-russian`. Future cross-language pairs
(English + Russian + Chinese versions of the same task) are a
candidate L0 expansion if multilingual fairness becomes an axis.

### 10. Streaming vs non-streaming output

| Effect | Where it bites |
|---|---|
| A few models behave subtly differently in streaming mode (stop sequences applied earlier, slight format drift). Usually cosmetic. | Negligible at L0; may matter for L2 skill-routing where event ordering is scored. |

**Action**: record `stream: bool` in trajectory. No L0 tagging
needed.

### 11. System-prompt injection by harness

| Effect | Where it bites |
|---|---|
| Even at T0 ("no operator config"), many runners prepend a default system prompt ("You are a helpful assistant"). At T1+ the operator CLAUDE.md is concatenated. Differences here partially explain "T0 vs T1" deltas that should ideally be zero. | All tasks at every tier. |

**Action**: trajectory must record the **verbatim** system prompt
the model saw. Track A responsibility. No L0 tagging.

### 12. Turn budget for multi-turn tasks

| Effect | Where it bites |
|---|---|
| Some tasks declare `max_turn_count` in scorer config. If the runner has its own lower hard cap, tasks may be cut off. | L0_607 (ask-before-destructive needs ≥2 turns), L0_303 (multi-tool ordering). |

**Action**: declare `max_turn_count` per task already done where
relevant. Document recommended runner-side cap = 10 for L0.

## How tags compose

A single task can carry multiple sensitivity tags. Example —
**L0_103 adversarial decoy NIAH**: `reasoning-sensitive`,
`context-window-sensitive`, `byte-exact-output`.

The leaderboard can then offer filters:
- "score on `reasoning-sensitive` subset only",
- "exclude `factual-recall` (avoid cutoff bias)",
- "show only tasks compatible with this runner's primitives".

## Recommended runner-side defaults

For honest cross-comparison, runners should default to:

```yaml
temperature: 0
top_p: 1.0
max_output_tokens: ≥ 4096
stream: false           # for scoring; streaming OK for UX
turn_cap: 10
reasoning_effort: auto  # but RECORD the actual budget used
```

and **record every value above** in `Trajectory.run_start`. Track A
should expand the Trajectory schema to require these fields. Until
then, expect cross-runner numbers to carry ±10 % systematic noise.
