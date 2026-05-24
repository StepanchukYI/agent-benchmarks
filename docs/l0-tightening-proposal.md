# L0 Tightening Proposal — Drop Opus 4-7 from ~96% to 60–70%

**Author**: Claude (Cowork session, 2026-05-24)
**Status**: Draft, awaiting approval before any YAML edits
**Target**: Move claude-opus-4-7 pass rate on L0 (n=104) from 91.3–96.2% to **60–70%**
**Hard constraint**: L0 task count must stay **≤ 120**. Default mode is *in-place* tightening; new tasks are added only by replacing existing ones one-for-one. Net-new tasks across all levers ≤ +16.
**Companion / supersedes**: relevant section of `agent_benchmarks_build_spec.md` (Phase 1 calibration)

---

## 1. Ground truth (what we actually saw)

From the leaderboard screenshot shared by the user (24 models × 5 pillars, n=104, 1 operator):

| Model | best % passed | worst % passed |
|---|---|---|
| claude-opus-4-7 (low) | **96.2%** (Correctness 99.5) | 91.3% (high effort) |
| claude-sonnet-4-6 (high) | 89.4% | 86.5% |
| claude-haiku-4-5 (low) | 87.5% | 85.6% |

**Memory pillar is blank for every model** — a structural gap, not a regression.

The user paraphrased the headline as "98%". The actual peak is 96.2%; the diagnosis below is the same either way.

## 2. Inventory of current L0

| Family (suite) | Count | What it tests |
|---|---|---|
| file-ops | 12 | byte-exact create / edit / rename / batch edit |
| schema-fill | 5 | JSON / YAML payload fill against schema |
| extract | 4 | pull a value from a structured file |
| exec | 4 | shell / pytest gates (only L0_004 actually runs pytest) |
| long-context-niah | 13 | needle-in-haystack ±decoys, depth 1–99% |
| long-context-multi-hop | 2 | two-hop fact tracing, variable rebinding |
| long-context-aggregation | 2 | sum / common-words across paragraphs |
| tool-use | 15 | function-calling args / order / coercion / refusal |
| instruction-following | 7 | nested / format-bound / negative-constraint chains |
| faithfulness | 10 | citation, hallucination spotting, source-quality |
| environment-probe | 15 | CLAUDE.md rule precedence / overrides |
| reasoning-trap | 15 | nested boolean, date arithmetic, graph colouring, trap Qs |
| **Total** | **104** | |

| Difficulty label | Count |
|---|---|
| easy | 26 |
| medium | 44 |
| hard | 34 |

Opus passes ~96% irrespective of label, which means the **label is descriptive of intent, not calibrated to model capability**. That is the first thing this proposal fixes.

## 3. Why Opus passes ~96% — five structural reasons

Confirmed by reading the YAMLs and the scorer code (`packages/ab-harness/ab_harness/scorers/*.py`):

### 3.1 The dominant correctness scorer is `final_assistant_message_equals`

- **46 / 104 tasks** rely on it. After `trim_whitespace`, an instruction-following model has exactly one string to hit.
- No negative twin (no "must NOT equal X"), no semantic equivalence check, no multiple right answers.

### 3.2 Secondary pillars almost never fail

`tool_skill` (`packages/ab-harness/ab_harness/scorers/tool_skill.py`):

```python
score = 1.0
if error_rate > 0.25:   score -= 0.5
if redundant_ratio > 0.5: score -= 0.3
if total_calls > max_tool_calls: score -= 0.2
# pass iff score >= pass_threshold (YAML default 0.5)
```

- L0 YAMLs override `pass_threshold` to **0.5 (127×), 0.4 (66×), 0.3 (47×)**. Pass thresholds ≥0.7 are used only 17 times across all assertions.
- Opus rarely produces >25% errored calls and almost never duplicates, so this gate is a free pass.

`latency_cost`: linear decay between `target_ms` and `max_ms`. `max_ms` distribution:

```
   3 × 45000
  36 × 60000
  27 × 90000
  10 × 120000
  14 × 180000
   6 × 150000
   3 × 240000
```

For tasks that take Opus 5–15 s, a 60–240 s ceiling means the latency scorer scores ≈1.0 every time. `max_cost_usd` is not set anywhere, so cost never bites.

`context_efficiency`: same linear-decay shape, with `max_tokens` mostly between 8 k and 20 k for tasks whose answer is a few tokens. The leaderboard "74 tok" / "81 tok" columns on Opus runs confirm context spend is well inside `target_tokens`.

### 3.3 Privacy pillar is binary and trivial

`privacy_check` runs `docs/privacy-patterns.yaml` against generated content. Synthetic L0 prompts emit no PII patterns. 100% pass.

### 3.4 Memory pillar is empty by design

- Only **10/104** L0 tasks have `weights.memory_specific > 0`.
- No L0 task triggers `skill_invocation_count` / `mcp_call_count_total` as a hard gate.
- Result: Memory column blank for every model, every run.

### 3.5 The "passing" predicate is two ORs that always co-fire

From `ab_sdk/results.py:269`:

```python
overall_pass = all_verdicts_pass and total_score >= 0.5
```

`all_verdicts_pass` is satisfied because all four secondary scorers pass with their low thresholds. `total_score >= 0.5` is satisfied because `correctness` weight is 0.75–0.85 and Opus's correctness pillar is 0.99.

→ The pass predicate effectively reduces to "did the final string equal expected?".

## 4. What the modern hard benchmarks do differently

(Sources at the bottom; the design ideas are reused, not the data.)

| Idea | Where seen | Effect on frontier pass rate |
|---|---|---|
| Multi-file / multi-line patches (avg 107 LOC, 4.1 files) | SWE-Bench Pro | Opus 4.5: 81% → 46% |
| `pass^k` (all k trials pass) instead of pass@1 | τ-bench / Tau² | GPT-4o tau-retail: 61% → 25% @ k=8 |
| Fresh post-cutoff problems | LiveCodeBench, LiveBench | HumanEval saturation defeated |
| Olympiad-tier with line-by-line failure annotation | LiveCodeBench Pro | Hard tier: 0% pass@1 for frontier |
| 5–6 simultaneous verifiable constraints | IFBench | "Strict accuracy" drops 20–40 pp vs IFEval |
| Real terminal execution, end-to-end | Terminal-Bench 2.0 | Opus 4.7: 68.5%, Opus 4.5: 58.4% |
| Multi-turn function calling with state | BFCL v3 | Top score ≈77% |
| RULER 13 long-context task types up to 128 k | NVIDIA RULER | Frontier effective context = 50–65% of advertised |
| Diff-format edits vs whole-file replace | Aider polyglot | Diff edit format drops scores ~10–15 pp |

Two structural patterns dominate the hard benchmarks:

1. **Verification is real execution, not text comparison.** Tests run, state diffs are computed, side-effects are checked.
2. **Reliability is measured over repetitions or simultaneous constraints**, not single runs.

L0 today has neither.

## 5. Strategy — three-lever tightening to land at 60–70%, count fixed at 104

I propose three independent levers. Each is scoped per-task-family. Predicted drops are explicit but require an A/B re-run on Opus to confirm.

**Count discipline**:

| Lever | Tasks touched | Tasks removed | Tasks added | Net Δ |
|---|---|---|---|---|
| A — stricter scorers | all 104 | 0 | 0 | **0** |
| B — replace saturated tasks | 27 | 27 | 27 | **0** (1-for-1) |
| C — engine-level scoring modes | all 104 (selectively) | 0 | 0 | **0** |
| **Total** | | **27** | **27** | **0** |

Final L0 task count after all three levers: **104** (unchanged). The 120-ceiling remains a 16-task emergency reserve, untouched by this proposal.

### 5.1 Lever A — stricter scorers on existing 104 tasks (~−15 pp)

Apply to **all 104 tasks** unless otherwise noted.

1. **Raise pass thresholds**
   - `tool_skill.pass_threshold`: 0.5 → **0.8** everywhere.
   - `context_efficiency.pass_threshold`: 0.3–0.4 → **0.6**.
   - `latency_cost.pass_threshold`: 0.3–0.4 → **0.6**.
   - **Mechanism**: scorers now actually penalise sloppy retries / oversized prompts / slow runs.
   - **Expected Opus drop**: −3 pp from `tool_skill` / `context_efficiency` alone. Opus low-effort runs already show 74–137 tok context, so most pass; but high-effort runs (134–199 tok) tighten near the line.

2. **Halve `max_tokens` and `max_ms`**
   - Cap by suite, not uniformly: NIAH/multi-hop suites can keep larger budgets, but tool-use / file-ops / reasoning-trap should run in **target × 2**, not `target × 5–10`.
   - **Expected Opus drop**: −2 pp. The signal is sharper on Sonnet/Haiku.

3. **Add forbidden-output assertion to every `*_equals` task**
   - Pattern: alongside the existing `final_assistant_message_equals: "X"`, add `final_assistant_message_does_not_contain` with 3–6 plausible-but-wrong answers, *including the question's distractor entities*.
   - Already done for L0_201 (`Roen`, `Idris`, `1822`, `since`). Backfill to the other 45 `*_equals` tasks.
   - **Expected Opus drop**: −2 pp. Opus often correctly emits the right answer with a trailing clause like " (from paragraph 13)" which currently passes after `trim_whitespace`; forbidden-list kills that.

4. **Add `final_assistant_message_word_count_max` for "Output ONLY X" tasks**
   - 38 tasks contain "Output ONLY" — cap final message at `len(expected_words) + 1` to penalise stealth prose.
   - **Expected Opus drop**: −1.5 pp.

5. **Convert eligible file-ops tasks from final-message check to `workdir_file_bytes_equal`**
   - L0_001, L0_002, L0_006, L0_010, L0_012 already use `workdir_file_*`. Extend to L0_008 (idempotent edit), L0_009 (atomic rename), L0_011 (three-way rotate). The byte-exact form catches CRLF / BOM / trailing-whitespace failures that text comparison currently absorbs.
   - **Expected Opus drop**: −1 pp.

6. **Activate Memory pillar on environment-probe (L0_601–615) and faithfulness (L0_501–510)**
   - Add `weights.memory_specific = 0.15` (taken from `correctness`) to all 25 of those tasks.
   - Add `skill_invocation_count` or `first_file_read` gating — agent must read CLAUDE.md / source.txt **before** first assistant text. We already have `_file_read_before_first_assistant_text` in `assertions.py:911`.
   - **Expected Opus drop**: −3 pp (Opus often answers without explicit Read, which currently doesn't penalise).

7. **Treat `redundant_ratio` more aggressively in `tool_skill`**
   - Edit `tool_skill.py:90`: change `if redundant_ratio > 0.5: score -= 0.3` to `> 0.25: -= 0.4`.
   - **Expected Opus drop**: −1 pp. Opus retries duplicate tool calls less than Sonnet, but does retry under high-effort thinking.

8. **Cost gate**
   - Add `max_cost_usd: 0.05` to non-NIAH suites (most non-long-context tasks should be sub-$0.01). `target_cost_usd: 0.01`.
   - **Expected Opus drop**: −1.5 pp at "high" effort (Opus burns more thinking budget).

**Lever A sub-total**: ~−15 pp ⇒ Opus ~81%.

### 5.2 Lever B — 1-for-1 replace 27 saturated tasks with harder analogues (~−15 pp)

Strict 1-for-1: each row drops one task ID and the harder replacement reuses the same ID slot. No net count change.

| Slot | Drop (why) | Replace with |
|---|---|---|
| L0_001 | trivial create-file | byte-exact create + must NOT touch existing fixture files (negative invariant) |
| L0_002 | trivial rename+edit | 3-file rename rotation with one symlinked entry to trip naive globs |
| L0_007 | trivial read with offset/limit | 4-segment read-and-stitch across non-contiguous byte ranges |
| L0_008 | idempotent edit (single file) | idempotent edit across 5 files; second run must produce zero diff |
| L0_020 | exec word-count one-shot | 3-step bash chain: filter → dedupe → count; intermediate file must exist + be cleaned up |
| L0_021 | exec csv-sum one-shot | csv-sum **with NaN / locale-formatted numbers** mixed in |
| L0_022 | exec sha256 fingerprint | sha256 of subset selected by another shell step (state dependency) |
| L0_101 | NIAH depth 25% | RULER-style needle @ depth 99% in **32 k haystack**, exact unit normalisation required |
| L0_104 | NIAH depth 1% variant | merge L0_104/105/106 into one: depth randomised per fixture seed |
| L0_105 | NIAH depth 50% variant | (merged into L0_104; this slot becomes a 4-needle simultaneous version) |
| L0_106 | NIAH depth 99% variant | (this slot becomes a near-collision needle that requires whole-noun-phrase match) |
| L0_110 | common words top-5 | top-5 with case-folded ties broken by first-appearance position |
| L0_202 | aggregation sum 17 numbers | sum of 23 numbers, **3 of them written in words** (twelve, thirty-four), plus 2 negatives |
| L0_301 | tool-call all required args | promote to **multi-turn** state dialog: 3 user turns, observed tool returns must drive next args |
| L0_302 | tool-call with optional arg | optional-arg gating by content of a prior return (state-diff dependency) |
| L0_303 | multi-tool call in order | strict ordered match (not subseq) + 2 interleaved distractor tools that look plausible |
| L0_307 | array-of-objects arg | array with **mixed valid + invalid items** — agent must filter, not pass-through |
| L0_311 | parallel independent calls | parallel calls with a shared output-key collision that requires distinct arg paths |
| L0_401 | nested instruction-following | promote to IFBench-style **6 simultaneous constraints**, all verifiable |
| L0_402 | word-bound output | word-bound + sentence-bound + forbidden-substring (3-axis) |
| L0_403 | format-bound JSON-only | JSON-only + top-level key order + field-word-count chain |
| L0_502 | verbatim among near-duplicates | near-duplicate paragraphs where only punctuation differs |
| L0_507 | inferred consistency check | three statements with two-step transitivity required to flag the inconsistency |
| L0_701 | nested boolean (one-shot) | 4-variable nested boolean with NOT-of-NOT + one decoy |
| L0_702 | logical deduction three | seven elements with one partial ordering and one constraint clue |
| L0_711 | modular arithmetic easy | chain three mods across cross-base conversions (base 2/8/10/16) |
| L0_712 | set difference easy | 12-element sets with multi-set semantics (duplicates count) |

The replacements all reuse existing scorer machinery + assertion kinds already defined in `packages/ab-harness/ab_harness/scorers/assertions.py`. No engine work. YAML + fixture authorship only.

**Expected Opus drop**: −15 pp. Bigger than the original −10 pp estimate because we replace 27 (not 20) tasks and each replacement is a confirmed harder design pattern from the 2026 benchmark literature.

### 5.3 Lever C — three engine-level scoring modes applied to existing tasks (~−10 pp)

Zero new tasks. Each mode is wired onto tasks that **already exist** (or onto the Lever-B replacements, which still occupy original slot IDs).

1. **`pass_k_reliability`** — re-run the same task ≥3 times in the same submission and require `passed_runs/k ≥ 0.66`. Applied at the runner level, not per-task, so it costs zero task slots. For a 96% pass@1 model with correlated failure modes, pass^3 lands around 85–88%.
   - **Effort**: ~80 LOC. New CLI flag `ab run --repeat 3`, new aggregator in `ab_sdk/results.py`. The published submission is per-(task, repetition); rescoring engine averages.
   - **Wire to**: every L0 task (no per-task config needed).
   - **Expected Opus drop**: −6 pp.

2. **`strict_format_diff`** — new assertion kind `final_assistant_message_is_unified_diff_applying_to(target, expected_bytes)`. Aider-style: model emits a unified diff, harness applies it server-side, compares bytes. Replaces the model's choice of write-tool vs final-message dump.
   - **Effort**: ~120 LOC + unit tests.
   - **Wire to**: 8 existing file-ops tasks — L0_003, L0_005, L0_006, L0_013, L0_014, L0_016, L0_017, L0_018. No new tasks, just an extra assertion in their `scorer_chain`.
   - **Expected Opus drop**: −2 pp on the wired subset (Opus diff format is mostly clean; Sonnet/Haiku drop more).

3. **`state_diff_chain`** — τ-bench style multi-turn state verification. Reuses the existing `workdir_file_*` assertions but anchors them to **post-Nth-user-turn** snapshots, so a single task asserts state at turns 2, 3, and 4 of a 4-turn dialogue.
   - **Effort**: ~150 LOC for the multi-turn fixture loader + per-turn assertion runner. Harness already supports multi-turn (see L0_310).
   - **Wire to**: L0_310 (existing) + the **4 Lever-B replacement slots** L0_301, L0_302, L0_303, L0_311 already designed as multi-turn variants (5 total). State-diff becomes the scorer for those promoted slots — zero net tasks.
   - **Expected Opus drop**: −2 pp.

**Lever C sub-total**: ~−10 pp. Task count Δ = **0**.

### 5.4 Combined expected outcome (task count stays at 104)

| Stage | Tasks | Opus 4-7 pass rate |
|---|---|---|
| Today (best run) | 104 | 96.2% |
| After Lever A (stricter scorers) | 104 | ~81% |
| After Lever A + B (replace 27 saturated tasks 1-for-1) | 104 | ~66% |
| After Lever A + B + C (new scoring modes wired onto existing tasks) | 104 | **~56–60%** |

This is the central estimate. Pessimistic / optimistic bands ±5 pp because we're predicting from mechanism, not from A/B data.

**Stop rule**: if Lever A+B alone lands inside 60–70%, **do not ship C** — over-tightening creates a benchmark frontier models can't move on, which is its own problem (LiveCodeBench Pro hard tier at 0% is unusable as a leaderboard signal). Given the revised Lever B estimate of ~66%, this is now the likely outcome and Lever C may be deferred to a future iteration.

## 6. Worked examples — what a tightened task + fixture actually looks like

User has explicitly overridden the prior "no benchmark content authorship" rule. I own all three levers end-to-end: YAML edits, new fixtures, new scorers, wiring.

### 6.1 Worked example A (L0_001)

**Current task (passes Opus trivially):**

```yaml
id: L0_001
title: "Create a file with exact specified content"
fixture_ref: "fixtures/repos/L0_smoke/L0_001/"   # empty workdir
scorer_chain:
  - name: file_diff
    config:
      expected:
        notes/greeting.txt: "Hello, Example.\n"
  - tool_skill: { max_tool_calls: 30, pass_threshold: 0.5 }
  - context_efficiency: { target: 2000, max: 20000, threshold: 0.3 }
  - latency_cost: { target: 30000, max: 180000, threshold: 0.3 }
```

**Tightened version (Lever A on the existing slot + Lever B replacement content):**

```yaml
id: L0_001
title: "Create file with exact content AND preserve every existing fixture file"
description: |
  The fixture seeds the workdir with:
      .keep            1 byte:  "X"
      README.fixture   312 bytes lorem ipsum
      data/seed.bin    64 random bytes (binary)

  Create a single new file at `notes/greeting.txt` with the exact
  byte-for-byte content `Hello, Example.\n`.

  Every other file in the workdir MUST remain byte-identical to its
  fixture state. Do not create, modify, rename, or delete any other file.
  No intermediate files (greeting.txt.tmp, .swp, .bak). No directory rename.

  Failure modes (the negative gates below catch these):
    - touching .keep ("cleaning up")
    - rewriting README.fixture
    - any byte change to data/seed.bin
    - creating extra intermediate files

fixture_ref: "fixtures/repos/L0_smoke/L0_001_v2/"

scorer_chain:
  - name: file_diff
    kind: deterministic
    config:
      expected:
        notes/greeting.txt: "Hello, Example.\n"

  - name: file_invariants
    kind: deterministic
    config:
      unchanged_from_fixture:
        - .keep
        - README.fixture
        - data/seed.bin

  - name: workdir_set_exact            # new assertion (Lever C)
    kind: deterministic
    config:
      allowed_paths_glob:
        - notes/greeting.txt
        - .keep
        - README.fixture
        - data/seed.bin
      forbidden_glob:
        - "**/*.tmp"
        - "**/*.bak"
        - "**/*.swp"

  - privacy_check: { patterns_path: "docs/privacy-patterns.yaml" }
  - tool_skill:         { max_tool_calls: 5, pass_threshold: 0.8 }   # was 30, 0.5
  - context_efficiency: { target: 2000, max: 6000, pass_threshold: 0.6 }  # was 20000, 0.3
  - latency_cost:       { target: 20000, max: 60000, pass_threshold: 0.6 } # was 180000, 0.3

weights:
  correctness: 0.70   # was 0.80
  tool_skill: 0.10
  context_efficiency: 0.10
  latency_cost: 0.10
  memory_specific: 0.00
```

**Fixture changes** (`fixtures/repos/L0_smoke/L0_001_v2/`):

```
.keep            ← 1 byte: "X"
README.fixture   ← 312 bytes of fixed lorem ipsum
data/seed.bin    ← 64 fixed random bytes (deterministic seed)
```

Fixture authorship is ~3 minutes per task for trivial seeds like this. The harder ones (NIAH @ 32 k haystack with random seed) take 20–30 min each.

### 6.2 Worked example B (L0_401 — IFBench-style 6-constraint)

**Current task (2 constraints, Opus passes):**

```yaml
description: |
  Write a paragraph about photosynthesis. Use exactly 50 words. Don't
  mention "chlorophyll".
scorer_chain:
  - final_assistant_message_word_count: { expected: 50 }
  - final_assistant_message_does_not_contain: { forbidden: ["chlorophyll"] }
```

**Tightened (6 simultaneous verifiable constraints, IFBench pattern):**

```yaml
description: |
  Write a paragraph about photosynthesis. ALL of the following must hold
  simultaneously — none of them is optional:
    1. Word count: exactly 60 words (Unicode-word, \w+).
    2. Sentence count: exactly 4 sentences (separated by . ! ?).
    3. Must NOT contain (case-insensitive): chlorophyll, sunlight,
       carbon dioxide, oxygen, plant, green.
    4. Must contain (case-sensitive): "ATP" once, "Calvin" once.
    5. First word starts with the letter "T".
    6. No markdown (no **, no ```, no leading "- " or "# ").
fixture_ref: null
scorer_chain:
  - name: ifbench_six_constraint
    kind: deterministic
    config:
      assertions:
        - kind: final_assistant_message_word_count:        { expected: 60 }
        - kind: final_assistant_message_sentence_count_range: { min: 4, max: 4 }
        - kind: final_assistant_message_does_not_contain_ci: { forbidden: [chlorophyll, sunlight, carbon dioxide, oxygen, plant, green] }
        - kind: final_assistant_message_contains_substring_verbatim: { substring: "ATP" }
        - kind: final_assistant_message_contains_substring_verbatim: { substring: "Calvin" }
        - kind: final_assistant_message_matches_any: { patterns: ["^T[a-z]"] }
        - kind: final_assistant_message_no_markdown:    {}
  - tool_skill:         { max_tool_calls: 0, pass_threshold: 1.0 }
  - context_efficiency: { target: 600, max: 2500, pass_threshold: 0.7 }
  - latency_cost:       { target: 10000, max: 30000, pass_threshold: 0.7 }
```

All six assertions use existing kinds in `assertions.py` — zero new engine code. The IFBench paper measures ~20–40 pp gap between "loose" (any constraint satisfied) and "strict" (all simultaneous). On Opus, the strict gate alone is expected to drop pass rate by ~5–8 pp on this task family of 7.

### 6.3 Fixture-authoring effort estimate per replacement

| Slot type | Fixture work | YAML work |
|---|---|---|
| `fixture_ref: null` (pure-prompt tasks like L0_401, L0_701, L0_711) | none | ~30 min each |
| trivial-seed fixtures (L0_001, L0_002, L0_008) | ~5–10 min | ~30 min |
| haystack fixtures (L0_101, L0_104–106 merged) | ~30–60 min (generator script) | ~30 min |
| multi-turn dialogue fixtures (L0_301, L0_302, L0_303, L0_310, L0_311) | ~60–90 min each (script the dialogue + assertions) | ~45 min |

**Total Lever-B authoring estimate**: ~25–35 hours of focused work for 27 tasks, depending on how much fixture generation is scripted vs hand-built. I do this myself; no handoff.

## 7. Sequencing and verification gates

1. **Lever A first** (lowest blast radius, no engine changes).
   - Edit 104 YAMLs.
   - `uv run pytest -q packages/ab-datasets/tests/test_pilot_tasks.py` must stay green.
   - Re-run Opus on the 104 — read the headline.
   - Decision point: if Opus ≤ 75%, stop and tune up; if 76–85%, proceed to Lever B.

2. **Lever B**: 1-for-1 replace 27 saturated YAML slots (I author all 27 YAMLs + fixtures, see §6). Same test loop. Confirm Sonnet stays ≥ 50% (don't kill the easier models entirely).

3. **Lever C**: scorer engine changes. Each new assertion ships with unit tests + VCR fixtures, per the project's "no live model calls in CI" rule.

4. **Verified trust tier**: every new scorer must implement both `.run(workdir, task, ...)` AND `.replay(traj_path, task, ...)` per LSN-007. `pass_k_reliability` needs special care — replay reuses the same trajectories, so the metric is deterministic.

5. **Schema export**: any new `assertions.kind` must update `docs/schemas/*.schema.json` via `make schema-export` (CI gate, per project conventions).

## 8. What I am NOT proposing

- **Not** moving L0 to SWE-Pro-level multi-file patches. That belongs at L4+ (composite). L0 is foundation skills.
- **Not** introducing LLM-judge. LSN-004 explicitly forbids LLM-judge as sole signal, and even paired it adds variance without much signal at L0 granularity.
- **Not** changing the 6-layer architecture (ADR-002) — only the L0 row of the matrix.

## 9. Open questions before edits

1. **Memory pillar**: activate on the 25 environment-probe + faithfulness tasks (Lever A.6), or keep it off until L1 work is on the table?
2. **`--repeat k`** (Lever C.1): acceptable given it 3× the run cost on every submission? If no, Lever C drops to ~−4 pp and we likely land at ~62%.
3. **Archive v1 YAMLs**: 27 original L0 task IDs will be repurposed (same ID, different content). Want me to keep the old YAMLs in `archive/L0_v1/` for replay reproducibility of pre-tightening submissions, or just overwrite?
4. **Forbidden-substring authorship**: I seed plausible distractors automatically from each task's `description.failure_modes` text, OR you want to review the lists manually before they go in?

Once I have answers I start Lever A on a branch. I'll auto-default to: Memory on, `--repeat k` deferred to v2 (cost concern), archive=yes, auto-seed forbidden lists. If any of those are wrong, override before I start.

---

## Sources

Long-context / reasoning gaps:
- [RULER: What's the Real Context Size of Your Long-Context Language Models? (arXiv 2404.06654)](https://arxiv.org/abs/2404.06654)
- [Long-Context LLM Benchmarks 2026 — past 200K tokens](https://ofox.ai/blog/long-context-llm-benchmarks-200k-tokens-2026/)

SWE-Bench family:
- [SWE-bench Pro Leaderboard 2026: Why 46% Beats 81%](https://www.morphllm.com/swe-bench-pro)
- [SWE-Bench 2026: Claude Opus 4.6 vs GPT-5.4](https://evolink.ai/blog/swe-bench-verified-2026-claude-vs-gpt)
- [Claude Benchmarks (2026): Opus 4.6, Sonnet 4.6 & Haiku](https://www.morphllm.com/claude-benchmarks)

Terminal-Bench 2.0:
- [Terminal-Bench 2.0 leaderboard](https://www.vals.ai/benchmarks/terminal-bench-2)
- [Terminal-Bench 2.0 — 21 model averages (BenchLM)](https://benchlm.ai/benchmarks/terminalBench2)
- [Agentic Coding Showdown: Claude Opus 4.7 vs GPT-5.5 on Terminal-Bench 2.0](https://www.padiso.co/blog/agentic-coding-showdown-claude-opus-4-7-vs-gpt-5-5-terminal-bench-swe-bench/)

τ-bench / Tau² / reliability metrics:
- [τ-bench: A Benchmark for Tool-Agent-User Interaction (arXiv 2406.12045)](https://arxiv.org/abs/2406.12045)
- [Pass@k vs Pass^k: Understanding Agent Reliability (Phil Schmid)](https://www.philschmid.de/agents-pass-at-k-pass-power-k)
- [Tau² blueprint for testing AI agents](https://quesma.com/blog/tau2-from-llm-benchmark-to-blueprint-for-testing-ai-agents/)
- [HAL: TAU-bench Airline leaderboard](https://hal.cs.princeton.edu/taubench_airline)

Function calling / multi-turn tool use:
- [BFCL-v3 Leaderboard 2026](https://pricepertoken.com/leaderboards/benchmark/bfcl-v3)
- [BFCL v3 Multi-turn Benchmark (Emergent Mind)](https://www.emergentmind.com/topics/bfcl-v3-multi-turn-benchmark)
- [BFCL_v3_MultiTurn Leaderboard (llm-stats)](https://llm-stats.com/benchmarks/bfcl-v3-multiturn)

Instruction-following hardness:
- [IFBench (Allen AI GitHub)](https://github.com/allenai/IFBench)
- [Instruction Following Leaderboard 2026](https://awesomeagents.ai/leaderboards/instruction-following-leaderboard/)
- [Generalizing Verifiable Instruction Following](https://www.themoonlight.io/en/review/generalizing-verifiable-instruction-following)

Aider polyglot / diff format:
- [Aider LLM Leaderboards](https://aider.chat/docs/leaderboards/)
- [Aider Polyglot (Epoch AI)](https://epoch.ai/benchmarks/aider-polyglot)
- [Aider Polyglot Score (Agile Leadership)](https://agileleadershipdayindia.org/blogs/ai-coding-benchmarks-decoded/aider-polyglot-benchmark-leaderboard.html)

Saturation, contamination, hard tiers:
- [LiveCodeBench Pro: Olympiad Medalists Judge LLMs (arXiv 2506.11928)](https://arxiv.org/pdf/2506.11928)
- [What is a Contaminated LLM (llm-stats)](https://llm-stats.com/blog/research/what-is-a-contaminated-llm)
- [What LLM Benchmarks Don't Measure — contamination, saturation, blind spots](https://benchmarkingagents.com/what-these-benchmarks-miss/)
- [AI Benchmarks 2026: Top Evaluations and Their Limits (Kili)](https://kili-technology.com/blog/ai-benchmarks-guide-the-top-evaluations-in-2026-and-why-theyre-not-enough)

METR / long-horizon:
- [Task-Completion Time Horizons of Frontier AI Models (METR)](https://metr.org/time-horizons/)
- [Measuring AI Ability to Complete Long Tasks (METR)](https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/)
- [METR Time Horizons (Epoch AI)](https://epoch.ai/benchmarks/metr-time-horizons)
