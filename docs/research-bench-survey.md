# Hard-task patterns survey — public benchmarks

Survey of public benchmarks consulted before designing the L0 hard
expansion. For each, we list the **patterns we lift** into L0
(deterministic, re-runnable, single-shot) and what we **deliberately
skip** because it pushes the task into L3/L4 territory.

## RULER (NVIDIA, 2024)

13 tasks across 4 categories: retrieval (NIAH variants), multi-hop
tracing (variable tracking), aggregation (common-word counting),
QA. Models claiming 32k+ context windows often degrade sharply past
8–16k effective length.

**Lift into L0:**
- multi-key NIAH (each key paired with a distinct value),
- multi-value NIAH (one key, several values, return all),
- variable tracking (`X = 7; Y = X; Z = Y; what is Z?` chain),
- common-words aggregation over a long word stream.

**Skip**: cross-document QA (drifts into L3 multi-hop with sources).

## BABILong (2024)

20 reasoning tasks at lengths from 1k to 50M tokens. Findings:
LLMs actually exploit only 10–20 % of their nominal context window;
performance falls sharply with reasoning depth.

**Lift into L0:**
- fact chaining at varying depth (1%, 50%, 99% of context),
- counting at depth,
- list / set membership.

**Skip**: 1M+ token variants (out of scope for L0 sandbox; would
need streaming).

## BIG-Bench Hard (BBH, 23 tasks)

Tasks where human baselines beat earlier LLMs. Categories: Boolean
expressions, logical deduction, geometric shapes, navigation,
temporal sequences, object counting, causal judgment, multi-step
arithmetic, snarks, ruin-names, salient-translation-error
detection, web-of-lies, etc.

**Lift into L0** as new `reasoning-trap` suite (L0_701..710):
- nested boolean expression (NOT chains),
- logical deduction puzzle (3 people, 3 attributes),
- causal judgment with multiple plausible causes,
- date arithmetic (subtract N days, cross year boundary),
- object counting with sub-set filter,
- navigation (do these instructions return to the start?),
- temporal sequence reordering,
- multi-step arithmetic with parentheses/negatives/fractions,
- table-read query (penguins-in-a-table style),
- web-of-lies / self-reference resolution.

**Skip**: ones that require image input (geometric shapes), domain
knowledge beyond high-school (movie recommendation).

## GPQA Diamond (198 questions)

PhD-level multi-choice in physics/chemistry/biology. Domain-expert
written. **Too narrow for L0** — L0 is foundation. We borrow the
**spirit** (questions resistant to web search, requiring multi-step
reasoning) into L0_70x trap design, but not the content.

## IFEval / FollowBench

FollowBench: 5 constraint types (Content / Scenario / Style /
Format / Example) added incrementally per level. IFEval: 25
verifiable instruction-following classes (word counts, json output,
specific phrase inclusion, language, case, repeat-prompt, etc.).

**Lift into L0** as hard variants in `instruction-following`
(L0_404..407):
- multi-constraint single prompt (exact-word-count AND
  no-comma AND no-proper-noun),
- explicit override-of-default constraint,
- format + content combined,
- negative constraint chain (avoid X AND Y AND Z).

**Skip**: live-language switching mid-response (too LLM-judge-y for
verified ceiling).

## BFCL v3 (Berkeley Function Calling, multi-turn)

1000 tests across vehicle / trading / travel / file-system domains.
State-based eval (DB diff). GLM-4.5 leads at 0.778 single-turn,
MiniMax M2.5 leads multi-turn at 0.768. Bug patterns: agents loop
(list dir, write, list again), re-ask for credentials.

**Lift into L0** as hard variants in `tool-use` (L0_309..315):
- deeply nested args (3 levels object-in-object),
- multi-turn state tracking (carry returned id across turns),
- parallel independent tool calls (3 in one turn),
- retry-on-transient-failure pattern,
- choose-the-right-tool from 10 similar names,
- stop-condition (don't loop),
- large argument payload (base64 binary).

**Skip**: domain-specific (banking workflow with policy doc) →
L3/L4.

## τ-bench (Sierra, retail / airline / banking)

Agent–user simulator with domain policy + tool API + DB. State-
based verification. Top models ≈ 35–61 %. Tests policy following
and multi-turn rule application.

**Lift into L0** as `environment-probe` hard variants (L0_609..615):
- two conflicting CLAUDE.md rules sharing a trigger,
- explicit user override of a default rule,
- rule precedence T2 vs T3 (T3 stricter),
- implicit rule inferred from a CLAUDE.md example block,
- rule + skill interaction (rule says ask before using skill X),
- multi-step rule (do A, then check B, then maybe C),
- rule with edge case ("X unless Z").

**Skip**: full simulated-user multi-turn dialogues → L3/L4.

## Pulling it together

L0 hard expansion target (≈ 40 new tasks):

| Group | New tasks | Source patterns |
|---|---|---|
| `long-context-*` depth curve | L0_104..110 (7) | RULER + BABILong |
| `reasoning-trap` new suite | L0_701..710 (10) | BBH + GPQA spirit |
| `file-ops` hard | L0_011..015 (5) | own design (multi-file atomic) |
| `tool-use` hard | L0_309..315 (7) | BFCL v3 |
| `instruction-following` hard | L0_404..407 (4) | IFEval + FollowBench |
| `faithfulness` hard | L0_506..510 (5) | own design (subtle hallucination, stale fact) |
| `environment-probe` hard | L0_609..615 (7) | τ-bench policy patterns |

Difficulty mix:
- **medium-hard** (target 60–80 % pass on top models): L0_104..106,
  L0_309..312, L0_404..406, L0_609..611.
- **frontier** (target 30–50 % pass even with reasoning=high):
  L0_107..110, L0_701..710, L0_313..315, L0_407, L0_506..510,
  L0_612..615.

All new tasks:
- pure-deterministic scorers (no LLM-judge in L0),
- byte-exact or numerically-exact assertions where possible,
- privacy_check + 3-pillar standard chain (tool_skill /
  context_efficiency / latency_cost),
- carry sensitivity tags per `docs/result-sensitivity-axes.md`.

## Sources

- [BBH: Challenging BIG-Bench Tasks (UK Government BEIS)](https://ukgovernmentbeis.github.io/inspect_evals/evals/reasoning/bbh/)
- [Challenging BIG-Bench Tasks and Whether CoT Can Solve Them (ACL 2023)](https://aclanthology.org/2023.findings-acl.824/)
- [RULER: What's the Real Context Size of Your Long-Context LMs? (Hsieh et al., 2024)](https://arxiv.org/abs/2404.06654)
- [BABILong: Testing the Limits of LLMs with Long Context Reasoning-in-a-Haystack](https://arxiv.org/html/2406.10149v1)
- [FollowBench: A Multi-level Fine-grained Constraints Following Benchmark (ACL 2024)](https://aclanthology.org/2024.acl-long.257/)
- [BFCL v3 Multi-Turn (Berkeley)](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html)
- [τ-bench: Tool-Agent-User Interaction (Sierra, ICLR 2025)](https://iclr.cc/virtual/2025/poster/28170)
- [GPQA: A Graduate-Level Google-Proof Q&A Benchmark](https://arxiv.org/abs/2311.12022)
