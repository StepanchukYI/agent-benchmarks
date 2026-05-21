# L0 layer inventory

39 tasks, 12 suites, all deterministic, all valid against the Pydantic
schema and the 8 repo-wide invariants in
`packages/ab-datasets/tests/test_pilot_tasks.py`.

`fixture_ref` paths are relative to `packages/ab-datasets/` (so the
prefix `fixtures/` is required, per `docs/adding-a-task.md` §3 and
the L0 convention).

## How to read this document

For every task we list **what it discriminates**, not just what it
does. L0 is a foundation layer — many tasks are floor checks (any
serious model passes them), some are discriminators between strong
and weak models on one tier, and some are paired mirror tasks where
the SAME prompt is expected to produce OPPOSITE behaviour at
different config tiers (tier-delta canary).

Legend:
- **floor** — any reasonable model on any tier should pass; failure
  indicates a fundamental regression (a useful canary, not a
  discriminator).
- **model-disc** — discriminates strong vs weak models on the same
  tier.
- **tier-delta** — discriminates the same model run at different
  tiers (T0 vs T2 vs T3). These probe whether the operator config
  reaches the model at all.
- **canary** — should produce an identical result at every tier; any
  divergence flags poisoning.

## file-ops (7 tasks)

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_001 | Create file with exact bytes from a content-only prompt | floor | T0 + T2 |
| L0_002 | Rename + minimal in-file edit, preserve unrelated content | floor / model-disc | T0 + T2 |
| L0_005 | Summarize a Python module into a 3-line README | model-disc | T0 + T2 |
| L0_006 | Append-only edit: preserve four prior lines byte-for-byte | model-disc | T0 + T2 |
| L0_007 | Offset/limit read: return exactly lines 100..109 of 200-line file | model-disc | T0 + T2 |
| L0_009 | Atomic rename, no `.tmp`/`.bak`/`.swp` residue | model-disc | T0 + T2 |
| L0_010 | UTF-8 unicode-safe write (Cyrillic + emoji), no BOM, no CRLF | model-disc | T0 + T2 |

## schema-fill (1 task)

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_003 | Fill a `version` field so `config.json` validates against `schema.json`; preserve `name` | floor | T0 + T2 |

## exec (1 task)

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_004 | Make a failing pytest pass; do not edit the test file itself | model-disc | T0 + T2 |

## extract (1 task)

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_005 | (counted under file-ops above; tagged `extract` historically) | — | — |

## idempotency (1 task)

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_008 | Apply the same write twice → same final JSON; rejects increment-by-1 semantics | model-disc | T0 + T2 |

## long-context-niah (3 tasks)

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_101 | Retrieve passphrase planted at ~25% depth in ~42 KB haystack | model-disc | T0 + T2 |
| L0_102 | Multi-needle (3 codes at ~18%/52%/86% depth) — order-sensitive | model-disc | T0 + T2 |
| L0_103 | Pick true fact, REJECT the adversarial decoy planted right beside it | model-disc (hallucination) | T0 + T2 |

## long-context-multi-hop (1 task)

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_201 | Two-hop chain Idris → cousin Roen → asset = Saltmoor lighthouse | model-disc | T0 + T2 |

## long-context-aggregation (1 task)

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_202 | Sum 17 inventory entries scattered across ~26 KB → ground truth 196 | model-disc | T0 + T2 |

## tool-use (8 tasks)

BFCL-style. The `tools.json` fixture file declares JSON Schemas for
the available tools; scorers compare emitted tool calls against those
schemas.

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_301 | Tool call with all required args (`create_user(email/username/age)`) | floor | T0 + T2 |
| L0_302 | Tool call passes one optional arg (`search_items(query, limit=5)`) | model-disc | T0 + T2 |
| L0_303 | Multi-tool ordering: `create_order` → `send_confirmation_email(order_id)` | model-disc | T0 + T2 |
| L0_304 | REFUSE tool call when required args are missing from prompt | model-disc | T0 + T2 |
| L0_305 | Number-as-string discipline: `set_temperature(celsius)` must be numeric | model-disc | T0 + T2 |
| L0_306 | Tool error recovery: report DNS failure honestly, do NOT fabricate result | model-disc (hallucination) | T0 + T2 |
| L0_307 | Array-of-objects argument with string-typed `value` (including `age="30"`) | model-disc | T0 + T2 |
| L0_308 | Enum value mapping: user says "urgent" → must send `high`/`critical`, never `urgent` | model-disc | T0 + T2 |

## instruction-following (3 tasks)

IFEval-style. Final assistant message must satisfy strict deterministic
constraints.

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_401 | Nested conditional ("do X then Y unless Z"); 7 ∈ [1..10] triggers `skip` | model-disc | T0 + T2 |
| L0_402 | Word-bound output: EXACTLY 14 whitespace tokens describing photosynthesis | model-disc | T0 + T2 |
| L0_403 | Format-bound: JSON only, no markdown fence, no surrounding prose | model-disc | T0 + T2 |

## faithfulness (5 tasks)

TruthfulQA-flavoured. Probes hallucination / fabrication vs honest
abstention or verbatim citation.

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_501 | Abstain when source does not break out churn per product line | model-disc (hallucination) | T0 + T2 |
| L0_502 | Cite a verbatim span: "the reduction in household-level sorting friction" | model-disc | T0 + T2 |
| L0_503 | Three contradicting sources → report disagreement, do NOT silently pick one | model-disc (hallucination) | T0 + T2 |
| L0_504 | Cite the correct paragraph identifier `[P2]`; reject `[P1]/[P3]/[P4]` | model-disc | T0 + T2 |
| L0_505 | Distinguish Olbrich's verbatim quote from critic's paraphrase | model-disc (misattribution) | T0 + T2 |

## environment-probe (8 tasks) — TIER-DELTA CORE

This is the layer's contribution to the runner-comparison axis.
Every task in this suite either depends on operator config being
present (T1+) or on it being absent (T0). The pair L0_605 / L0_606
is the sharpest tier-delta probe in L0: same prompt, opposite
required behaviour.

| ID | What it measures | Discriminator | Tier coverage |
|---|---|---|---|
| L0_601 | At T1+, agent reads CLAUDE.md/AGENTS.md BEFORE first assistant text | tier-delta | T1 + T2 + T3 |
| L0_602 | At T0 (no CLAUDE.md), agent does NOT invent "according to your rules" prose | model-disc / tier-delta | T0-only |
| L0_603 | At T2/T3, follows positive rule "always cite sources" → answer + citation | tier-delta | T2 + T3 |
| L0_604 | At T2/T3, follows negative rule "never use emojis" even when user uses one | tier-delta | T2 + T3 |
| L0_605 | At T0, no fake skill invocation for "запиши решение" (no skill installed) | tier-delta (mirror of 606) | T0-only |
| L0_606 | At T2/T3, DOES dispatch to `memory:memory-write` for "запиши решение" | tier-delta (mirror of 605) | T2 + T3 |
| L0_607 | At T2/T3, respects "ask before deleting" rule → confirmation before tool call | tier-delta | T2 + T3 |
| L0_608 | Cross-tier factual canary: gold = `Au` at every tier, divergence flags poisoning | canary | T0 + T1 + T2 + T3 |

## Tier coverage summary

| Tier | Tasks where this tier is in scope |
|---|---|
| T0 (vanilla) | all `file-ops`, `schema-fill`, `exec`, `extract`, `idempotency`, `long-context-*`, `tool-use`, `instruction-following`, `faithfulness`; environment-probes 602, 605, 608 |
| T1 (minimal) | 601, 608 |
| T2 (personal) | everything except 605 (T0-only) and 602 (T0-only) |
| T3 (full) | 601, 603, 604, 606, 607, 608 |

## Discriminator inventory

- **Hallucination probes** (rejects fabrication on absent/ambiguous info):
  L0_103, L0_306, L0_501, L0_503, L0_505, L0_602, L0_605.
- **Tier-delta pairs** (proof that operator config reaches the model):
  L0_605 ↔ L0_606 (mirror), L0_603, L0_604, L0_607 (rule-following),
  L0_601 (auto-context).
- **Tier-poisoning canaries** (must produce identical answer across
  tiers, divergence flags issue): L0_608.
- **Format / instruction discipline**: L0_401, L0_402, L0_403, L0_502,
  L0_504, L0_505.
- **Tool-use discipline** (BFCL-style): L0_301..L0_308.
- **Long-context capability**: L0_101..L0_103, L0_201, L0_202.

## Sensitivity-tag axes (docs/result-sensitivity-axes.md)

These tags capture **secondary axes** that move scores in ways not
captured by (model × runner × tier × task). Locked by
`tests/test_l0_sensitivity_tags.py`.

| Tag | Meaning | Count | Tasks |
|---|---|--:|---|
| `reasoning-sensitive` | Scaling with thinking budget / reasoning effort | 19 | L0_101, 102, 103, 201, 202, 303, 304, 305, 306, 307, 308, 401, 402, 501, 503, 602, 604, 605, 607 |
| `byte-exact-output` | Scorer requires byte-equal output; flaky under temperature > 0 | 16 | L0_001, 002, 006, 007, 010, 101, 102, 103, 201, 202, 401, 402, 403, 502, 505, 608 |
| `output-normalization-sensitive` | Trim/wrap/markdown-fence from runner can defeat byte-exact scoring | 16 | (same as byte-exact-output) |
| `context-window-sensitive` | Haystack 12–42 KB; needs ≥16k context window | 5 | L0_101, 102, 103, 201, 202 |
| `factual-recall` | Answer depends on model knowledge (training cutoff) | 3 | L0_603 (Eiffel 1889), L0_608 (Au) |
| `runner-skill-dispatch` | Requires runner primitive: `skill_invocation` events | 2 | L0_605, L0_606 |
| `language-russian` | Prompt is in Russian (multilingual model required) | 2 | L0_605, L0_606 |
| `tokenizer-sensitive` | Score depends on token-count definition (whitespace) | 1 | L0_402 |

Tasks **without any sensitivity tag** (the simple-capability subset)
are: L0_003, L0_004, L0_005, L0_008, L0_009, L0_301, L0_302, L0_504,
L0_601. These are the foundational floor checks; failure on these
indicates a fundamental capability gap, not an axis bias.

## What L0 does NOT cover

- Memory write/retrieve discipline → L1 layer.
- Skill orchestration across multiple skills → L2 layer.
- Domain-specific systems (Obsidian, Lantern, GitNexus, Graphify) → L3 layer.
- Multi-session continuity → L1_30x + L4 composite.
- Subtle differences between top-tier models (Claude 4.6 vs 4.7, GPT-5,
  Gemini 2.5) on long horizons → L4 composite.

L0's job is to certify that a runner/model combination is **useful as
an agent at all** and to expose where operator configuration actually
reaches the model. Once L0 is passing for a runner, climb the layers.

## See also

- `docs/architecture.md` — high-level package layout.
- `docs/config-tiers.md` — ADR-008 tier semantics.
- `docs/trust-tiers.md` — per-layer trust ceilings.
- `docs/adding-a-task.md` — authoring new tasks.
- `docs/fixtures-todo.md` — open fixture work for L1+.
- `packages/ab-datasets/fixtures/manifest.yaml` — SHA256 manifest.
- `packages/ab-datasets/tests/test_pilot_tasks.py` — repo-wide
  invariants every task must satisfy.
