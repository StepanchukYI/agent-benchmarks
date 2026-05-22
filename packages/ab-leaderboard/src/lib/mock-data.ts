/**
 * Mock data for the SPA while the live `/api/v1/*` endpoints are still being
 * wired up. Every shape here matches `src/lib/types.ts` which in turn mirrors
 * `docs/schemas/*.schema.json`.
 *
 * Replace one collection at a time with a real `useQuery`-backed loader; the
 * page-level components consume these arrays directly and have no other state.
 *
 * Privacy note (LSN-006): the example paths in `SCRUBBER_FINDS` are intentional
 * placeholders demonstrating what the scrubber catches; they are not real
 * filesystem paths.
 */

import type {
  AlertRule,
  LeaderboardRow,
  Model,
  Operator,
  RegistryRepo,
  RegressionItem,
  RunSummary,
  ScrubberFinding,
  ScrubberRule,
  Suite,
  Task,
  Trajectory,
} from "./types";

export const PILLARS = ["Correctness", "Context", "Tool/Skill", "Memory", "Cost"] as const;
export type Pillar = (typeof PILLARS)[number];

export const MODELS: Model[] = [
  { id: "claude-sonnet-4-5",  short: "Sonnet 4.5",  vendor: "anthropic", harness: "Claude Code",    capabilities: ["MCP-native", "tool-use"],  cost_per_1k_in: 3.0,  cost_per_1k_out: 15.0 },
  { id: "claude-opus-4-1",    short: "Opus 4.1",    vendor: "anthropic", harness: "Claude Code",    capabilities: ["MCP-native", "tool-use"],  cost_per_1k_in: 15.0, cost_per_1k_out: 75.0 },
  { id: "gpt-5",              short: "GPT-5",       vendor: "openai",    harness: "Codex CLI",      capabilities: ["FC-native", "MCP"],        cost_per_1k_in: 2.5,  cost_per_1k_out: 10.0 },
  { id: "o3",                 short: "o3",          vendor: "openai",    harness: "Codex CLI",      capabilities: ["FC-native", "reasoning"],  cost_per_1k_in: 10.0, cost_per_1k_out: 40.0 },
  { id: "gemini-2.5-pro",     short: "Gemini 2.5",  vendor: "google",    harness: "Gemini CLI",     capabilities: ["FC-native", "MCP"],        cost_per_1k_in: 1.25, cost_per_1k_out: 10.0 },
  { id: "glm-4-6",            short: "GLM-4.6",     vendor: "zhipu",     harness: "OpenAI-compat",  capabilities: ["FC-native"],               cost_per_1k_in: 0.6,  cost_per_1k_out: 2.2 },
  { id: "minimax-m2",         short: "MiniMax-M2",  vendor: "minimax",   harness: "FC + MCP shim",  capabilities: ["FC-native", "shim"],       cost_per_1k_in: 0.3,  cost_per_1k_out: 1.2 },
];

export const SUITES: Suite[] = [
  { id: "L0_smoke",         layer: "L0", name: "Smoke",         description: "File ops, schema, IFEval subset",  task_count: 22 },
  { id: "L0_niah",          layer: "L0", name: "NIAH / RULER",  description: "Long-context needle retrieval",     task_count: 18 },
  { id: "L1_memory_write",  layer: "L1", name: "Memory write",  description: "Decision + lesson schema fidelity", task_count: 25 },
  { id: "L1_retrieval",     layer: "L1", name: "Retrieval",     description: "Hierarchical vault retrieval",      task_count: 14 },
  { id: "L1_consolidation", layer: "L1", name: "Consolidation", description: "Contradiction + merge",             task_count: 11 },
  { id: "L2_mcp",           layer: "L2", name: "MCP routing",   description: "User-owned server selection",       task_count: 17 },
  { id: "L3_skills",        layer: "L3", name: "Skill trigger", description: "Router precision / recall",         task_count: 19 },
  { id: "L4_end_to_end",    layer: "L4", name: "End-to-end",    description: "Daily workflow scenarios",          task_count: 8 },
];

export const OPERATORS: Operator[] = [
  { handle: "demo-operator",   name: "Demo Operator",   initials: "DO", color: "#3b82f6", repo: "github.com/example/agent-benchmarks-results", trust_default: "official",      is_self: true },
  { handle: "rachel-yeh",      name: "Rachel Yeh",      initials: "RY", color: "#ec4899", repo: "github.com/rachel-yeh/ab-runs",               trust_default: "verified" },
  { handle: "noamb",           name: "Noam B.",         initials: "NB", color: "#10b981", repo: "github.com/noamb/agent-bench-results",         trust_default: "verified" },
  { handle: "kpyrne",          name: "Kira Pyrne",      initials: "KP", color: "#f59e0b", repo: "github.com/kpyrne/ab-eval",                    trust_default: "self_reported" },
  { handle: "ssaroliya",       name: "S. Saroliya",     initials: "SS", color: "#8b5cf6", repo: "github.com/ssaroliya/personal-bench",          trust_default: "self_reported" },
  { handle: "djun-kim",        name: "Djun Kim",        initials: "DK", color: "#06b6d4", repo: "github.com/djun-kim/agent-bench",              trust_default: "verified" },
  { handle: "anthropic-labs",  name: "Anthropic Labs",  initials: "AL", color: "#d97757", repo: "github.com/anthropic-labs/ab-public",          trust_default: "official" },
];

export function operatorByHandle(handle: string): Operator | undefined {
  return OPERATORS.find((o) => o.handle === handle);
}
export function modelById(id: string): Model | undefined {
  return MODELS.find((m) => m.id === id);
}

export const LEADERBOARD: LeaderboardRow[] = [
  { model: "claude-opus-4-1",   operator: "demo-operator",     trust_tier: "official",     source_commit_sha: "a7c2b09", tier: "T2", scores: [89.4, 84.1, 91.2, null, 62.5], delta: [+1.2, +0.4, +2.1, null, -3.1], runs: 412, variance: 1.8, cost_per_task: 0.0982, latency_s: 26.3, sweep_cost: 4.21, dataset_pin: { version: "v1.0", behind: 0 }, tokens_total: 48200, turns_total: 23, pass_rate: 71.2, pillar_counts: [412, 412, 401,   0, 389] },
  { model: "claude-sonnet-4-5", operator: "demo-operator",     trust_tier: "official",     source_commit_sha: "a7c2b09", tier: "T2", scores: [87.1, 82.6, 88.4, 84.2, 78.1], delta: [+2.1, +1.6, +0.9, +1.3, +0.4], runs: 489, variance: 2.1, cost_per_task: 0.0241, latency_s: 14.8, sweep_cost: 1.12, dataset_pin: { version: "v1.0", behind: 0 }, tokens_total: 31500, turns_total: 18, pass_rate: 68.9, pillar_counts: [489, 489, 482, 476, 471] },
  { model: "gpt-5",             operator: "demo-operator",     trust_tier: "verified",     source_commit_sha: "3f81e44", tier: "T2", scores: [85.6, 86.0, 84.7, null, 81.4], delta: [+0.4, +2.2, -0.6, null, +1.2], runs: 421, variance: 2.4, cost_per_task: 0.0298, latency_s: 17.5, sweep_cost: 1.31, dataset_pin: { version: "v1.0", behind: 0 }, tokens_total: 39800, turns_total: 21, pass_rate: 66.4, pillar_counts: [421, 421, 418,   0, 409] },
  { model: "o3",                operator: "rachel-yeh",        trust_tier: "verified",     source_commit_sha: "d9a1c02", tier: "T2", scores: [88.2, 83.7, 86.1, 81.6, 58.2], delta: [+0.8, -0.3, +1.4, +2.1, -2.4], runs: 318, variance: 1.9, cost_per_task: 0.118,  latency_s: 38.2, sweep_cost: 4.96, dataset_pin: { version: "v0.9", behind: 2 }, tokens_total: 52100, turns_total: 27, pass_rate: 70.1, pillar_counts: [318, 318, 314, 309, 302] },
  { model: "gemini-2.5-pro",    operator: "noamb",             trust_tier: "verified",     source_commit_sha: "1e0f7a8", tier: "T1", scores: [82.4, 88.2, 80.5, 76.8, 84.6], delta: [-0.7, +1.1, -2.3, -0.4, +0.7], runs: 402, variance: 2.6, cost_per_task: 0.0189, latency_s: 11.2, sweep_cost: 0.78, dataset_pin: { version: "v1.0", behind: 0 }, tokens_total: 28700, turns_total: 16, pass_rate: 63.8, pillar_counts: [402, 402, 398, 391, 388] },
  { model: "glm-4-6",           operator: "kpyrne",            trust_tier: "self_reported", source_commit_sha: "b240cf6", tier: "T0", scores: [74.8, 71.3, 76.2, 69.5, 91.4], delta: [+3.4, +0.8, +1.9, +2.6, -0.2], runs: 376, variance: 3.1, cost_per_task: 0.0052, latency_s: 9.4,  sweep_cost: 0.22, dataset_pin: { version: "v0.8", behind: 3 }, tokens_total: 22400, turns_total: 14, pass_rate: 54.2, pillar_counts: [376, 376, 369, 362, 358] },
  { model: "minimax-m2",        operator: "djun-kim",          trust_tier: "verified",     source_commit_sha: "7b3d551", tier: "T2", scores: [68.1, 64.5, 71.8, null, 94.2], delta: [+1.9, +2.4, +0.4, null, +0.1], runs: 341, variance: 3.4, cost_per_task: 0.0027, latency_s: 7.8,  sweep_cost: 0.11, dataset_pin: { version: "v1.0", behind: 0 }, tokens_total: 19800, turns_total: 12, pass_rate: 49.7, pillar_counts: [341, 341, 337,   0, 330] },
];

function seededTrend(seed: number, base: number, drift: number, noise: number): number[] {
  const arr: number[] = [];
  let v = base;
  let s = seed;
  for (let i = 0; i < 30; i++) {
    s = (s * 9301 + 49297) % 233280;
    const r = s / 233280;
    v += drift + (r - 0.5) * noise;
    v = Math.max(40, Math.min(98, v));
    arr.push(+v.toFixed(2));
  }
  return arr;
}

export const TRENDS: Record<string, number[]> = {
  "claude-opus-4-1":   seededTrend(11, 86, 0.10, 2.4),
  "claude-sonnet-4-5": seededTrend(22, 83, 0.13, 2.1),
  "gpt-5":             seededTrend(33, 84, 0.06, 2.8),
  "o3":                seededTrend(44, 87, 0.04, 1.9),
  "gemini-2.5-pro":    seededTrend(55, 80, 0.08, 3.0),
  "glm-4-6":           seededTrend(66, 71, 0.13, 3.4),
  "minimax-m2":        seededTrend(77, 65, 0.10, 3.6),
};

export const OPERATOR_TRENDS: Record<string, number[]> = {
  "demo-operator": TRENDS["claude-sonnet-4-5"]!,
  "rachel-yeh":  seededTrend(101, 81, 0.07, 2.4),
  "noamb":       seededTrend(102, 78, 0.04, 2.2),
  "djun-kim":    seededTrend(103, 83, 0.12, 2.9),
  "kpyrne":      seededTrend(104, 76, -0.02, 3.4),
  "ssaroliya":   seededTrend(105, 74, 0.06, 3.6),
};

export const RECENT_RUNS: RunSummary[] = [
  { run_id: "ab-2026-21-04", suite: "L0+L1 full sweep", model_count: 5, status: "completed", started_at: "2026-05-21T09:14:00Z", duration_min: 38, cost_usd: 4.21, score: 84.6, delta: +1.2 },
  { run_id: "ab-2026-21-03", suite: "L1_memory_write",  model_count: 7, status: "completed", started_at: "2026-05-21T07:02:00Z", duration_min: 22, cost_usd: 1.87, score: 81.2, delta: -0.4 },
  { run_id: "ab-2026-21-02", suite: "L2_mcp + L3_skills", model_count: 3, status: "error",   started_at: "2026-05-21T03:48:00Z", duration_min: 41, cost_usd: 2.34, score: 71.4, delta: -6.8 },
  { run_id: "ab-2026-20-09", suite: "Smoke (CI)",       model_count: 5, status: "completed", started_at: "2026-05-20T18:11:00Z", duration_min: 4,  cost_usd: 0.18, score: 96.1, delta: +0.2 },
  { run_id: "ab-2026-20-08", suite: "L0+L1 full sweep", model_count: 5, status: "timeout",   started_at: "2026-05-20T11:23:00Z", duration_min: 39, cost_usd: 4.18, score: 83.4, delta: +0.8 },
  { run_id: "ab-2026-20-07", suite: "L4_end_to_end",    model_count: 2, status: "completed", started_at: "2026-05-20T08:01:00Z", duration_min: 27, cost_usd: 3.21, score: 79.1, delta: +2.4 },
  { run_id: "ab-2026-19-06", suite: "Smoke (CI)",       model_count: 5, status: "completed", started_at: "2026-05-19T17:42:00Z", duration_min: 4,  cost_usd: 0.17, score: 95.9, delta: -0.1 },
  { run_id: "ab-2026-19-05", suite: "L1_retrieval",     model_count: 4, status: "completed", started_at: "2026-05-19T12:18:00Z", duration_min: 19, cost_usd: 1.42, score: 80.3, delta: +1.6 },
];

export const PRIVATE_TASK_IDS = new Set([
  "L1_003", "L1_101", "L1_102", "L1_201", "L1_202",
]);

function mkTask(input: Omit<Task, "config" | "visibility"> & { required_tier?: "T0" | "T1" | "T2" | "T3"; recommended_tier?: "T0" | "T1" | "T2" | "T3" }): Task {
  return {
    ...input,
    visibility: PRIVATE_TASK_IDS.has(input.id) ? "private" : "public",
    config: {
      required_tier: input.required_tier ?? "T0",
      recommended_tier: input.recommended_tier ?? "T2",
    },
  };
}

export const TASKS: Task[] = [
  // L0 — smoke
  mkTask({ id: "L0_001", layer: "L0", suite: "L0_smoke", title: "Atomic file write with frontmatter",       description: "Write a file with a YAML frontmatter block; preserve trailing newline.",                         difficulty: "easy",   trust_tier_ceiling: "official", pass_rate: 98, scorer_chain: [{ name: "state_diff", kind: "state_diff" }, { name: "privacy_check", kind: "privacy_check" }] }),
  mkTask({ id: "L0_002", layer: "L0", suite: "L0_smoke", title: "Schema-validate decision YAML",            description: "Validate frontmatter against decision.v2.json.",                                                  difficulty: "easy",   trust_tier_ceiling: "official", pass_rate: 96, scorer_chain: [{ name: "schema", kind: "schema" }] }),
  mkTask({ id: "L0_003", layer: "L0", suite: "L0_smoke", title: "IFEval — exact line-count constraint",     description: "Produce output matching a hard line-count cap.",                                                  difficulty: "easy",   trust_tier_ceiling: "official", pass_rate: 91, scorer_chain: [{ name: "exec_check", kind: "exec" }] }),
  mkTask({ id: "L0_004", layer: "L0", suite: "L0_smoke", title: "Round-trip JSON ↔ YAML preserves order",   description: "Open-ended structural fidelity check.",                                                          difficulty: "medium", trust_tier_ceiling: "official", pass_rate: 84, scorer_chain: [{ name: "exec_check", kind: "exec" }] }),
  mkTask({ id: "L0_005", layer: "L0", suite: "L0_smoke", title: "Idempotent edit (run twice → same hash)",  description: "Second run must produce zero diff.",                                                              difficulty: "medium", trust_tier_ceiling: "official", pass_rate: 79, scorer_chain: [{ name: "state_diff", kind: "state_diff" }] }),
  // L0 — niah
  mkTask({ id: "L0_101", layer: "L0", suite: "L0_niah",  title: "Needle @ depth 25% in 32k context",        description: "Retrieve a known phrase from synthetic noise.",                                                   difficulty: "easy",   pass_rate: 99, scorer_chain: [{ name: "exec_check", kind: "exec" }] }),
  mkTask({ id: "L0_102", layer: "L0", suite: "L0_niah",  title: "Multi-needle (3) @ random depths, 64k",    description: "Retrieve 3 needles, scored individually.",                                                        difficulty: "medium", pass_rate: 86, scorer_chain: [{ name: "exec_check", kind: "exec" }] }),
  mkTask({ id: "L0_103", layer: "L0", suite: "L0_niah",  title: "Adversarial needle near distractor, 128k", description: "Distractor sentence inserted near the target.",                                                   difficulty: "hard",   pass_rate: 64, scorer_chain: [{ name: "exec_check", kind: "exec" }] }),
  // L1 — memory write
  mkTask({ id: "L1_001", layer: "L1", suite: "L1_memory_write", title: "Write decision: Postgres vs SQLite", description: "Capture an ADR for choosing Postgres in v1; supersedes db-choice.",                              difficulty: "medium", required_tier: "T2", trust_tier_ceiling: "verified", pass_rate: 82, scorer_chain: [{ name: "schema", kind: "schema" }, { name: "state_diff", kind: "state_diff" }, { name: "privacy_check", kind: "privacy_check" }] }),
  mkTask({ id: "L1_002", layer: "L1", suite: "L1_memory_write", title: "Write lesson with prior-art links",  description: "Lesson must link a prior decision and at least one external reference.",                          difficulty: "medium", required_tier: "T2", trust_tier_ceiling: "verified", pass_rate: 76, scorer_chain: [{ name: "schema", kind: "schema" }, { name: "consistency", kind: "llm_judge" }] }),
  mkTask({ id: "L1_003", layer: "L1", suite: "L1_memory_write", title: "Append-only edit preserves history",  description: "Edit a decision without losing the prior status block.",                                          difficulty: "hard",   required_tier: "T2", trust_tier_ceiling: "verified", pass_rate: 71, scorer_chain: [{ name: "state_diff", kind: "state_diff" }] }),
  mkTask({ id: "L1_004", layer: "L1", suite: "L1_memory_write", title: "Frontmatter: enforce `status` enum", description: "Reject invalid status values.",                                                                    difficulty: "easy",   required_tier: "T2", pass_rate: 93, scorer_chain: [{ name: "schema", kind: "schema" }] }),
  // L1 — retrieval (private)
  mkTask({ id: "L1_101", layer: "L1", suite: "L1_retrieval", title: "Hierarchical retrieval — pick 3 of 47", description: "Find the 3 most relevant prior notes in a vault snapshot.",                                       difficulty: "medium", required_tier: "T2", trust_tier_ceiling: "self_reported", pass_rate: 73, scorer_chain: [{ name: "exec_check", kind: "exec" }, { name: "relevance", kind: "llm_judge" }] }),
  mkTask({ id: "L1_102", layer: "L1", suite: "L1_retrieval", title: "Disambiguate two decisions on same topic", description: "Pick the non-superseded one.",                                                                  difficulty: "hard",   required_tier: "T2", trust_tier_ceiling: "self_reported", pass_rate: 58, scorer_chain: [{ name: "disambig", kind: "llm_judge" }] }),
  // L1 — consolidation (private)
  mkTask({ id: "L1_201", layer: "L1", suite: "L1_consolidation", title: "Detect & resolve contradiction (2 sources)", description: "Reconcile two decisions that disagree.",                                                  difficulty: "hard",   required_tier: "T2", trust_tier_ceiling: "self_reported", pass_rate: 54, scorer_chain: [{ name: "reconcile", kind: "llm_judge" }] }),
  mkTask({ id: "L1_202", layer: "L1", suite: "L1_consolidation", title: "Merge 3 lessons into a principle",         description: "Produce a higher-level rule covering 3 lessons.",                                          difficulty: "hard",   required_tier: "T2", trust_tier_ceiling: "self_reported", pass_rate: 49, scorer_chain: [{ name: "principle", kind: "llm_judge" }] }),
  // L2 — MCP routing
  mkTask({ id: "L2_001", layer: "L2", suite: "L2_mcp",   title: "Route to GitNexus vs Graphify on repo query", description: "Select the better-suited MCP server.",                                                          difficulty: "medium", required_tier: "T2", pass_rate: 78, scorer_chain: [{ name: "exec_check", kind: "exec" }] }),
  mkTask({ id: "L2_002", layer: "L2", suite: "L2_mcp",   title: "Detect missing MCP capability, ask for it",   description: "Recognize when no installed MCP can handle the query.",                                          difficulty: "medium", required_tier: "T2", pass_rate: 64, scorer_chain: [{ name: "capability", kind: "llm_judge" }] }),
  // L3 — skills
  mkTask({ id: "L3_001", layer: "L3", suite: "L3_skills", title: "Trigger correct skill from ambiguous prompt", description: "Router must pick the right skill among 47.",                                                   difficulty: "medium", required_tier: "T2", pass_rate: 71, scorer_chain: [{ name: "exec_check", kind: "exec" }] }),
  mkTask({ id: "L3_002", layer: "L3", suite: "L3_skills", title: "Reject decoy: do NOT trigger skill X",        description: "Adversarial prompt designed to mis-fire.",                                                     difficulty: "medium", required_tier: "T2", pass_rate: 83, scorer_chain: [{ name: "exec_check", kind: "exec" }] }),
];

export function tasksBySuite(suiteId: string): Task[] {
  return TASKS.filter((t) => t.suite === suiteId);
}
export function tasksByLayer(layer: string): Task[] {
  return TASKS.filter((t) => t.layer === layer);
}
export function taskById(id: string): Task | undefined {
  return TASKS.find((t) => t.id === id);
}

export const TRAJECTORY: Trajectory = {
  task: TASKS.find((t) => t.id === "L1_001")!,
  model: MODELS.find((m) => m.id === "claude-sonnet-4-5")!,
  operator: "demo-operator",
  run_id: "ab-2026-21-04",
  source_repo: "github.com/example/agent-benchmarks-results",
  source_commit_sha: "a7c2b09",
  tier: "T2",
  trust_tier: "official",
  status: "completed",
  duration_s: 18.4,
  cost_usd: 0.0868,
  tokens_in: 12480,
  tokens_out: 2104,
  pillar_scores: { Correctness: 92, Context: 88, "Tool/Skill": 95, Memory: 89, Cost: 81 },
  turns: [
    { idx: 1, role: "system",    kind: "prompt",  label: "System prompt + task",                        meta: "tokens 4 210",            icon: "file-text" },
    { idx: 2, role: "assistant", kind: "tool",    label: "glob(**/decisions/*.md)",                     meta: "returned 14 files · 0.4s", icon: "cube" },
    { idx: 3, role: "assistant", kind: "read",    label: "read(\"decisions/db-choice.md\")",            meta: "1.2 KB · 0.1s",           icon: "file-text" },
    { idx: 4, role: "assistant", kind: "thought", label: "Model: identifies decision schema",            meta: "tokens out 312",          icon: "brain" },
    { idx: 5, role: "assistant", kind: "read",    label: "read(\"templates/decision.md\")",             meta: "0.6 KB · 0.1s",           icon: "file-text" },
    { idx: 6, role: "assistant", kind: "write",   label: "write(\"decisions/postgres-vs-sqlite.md\")",  meta: "+47 lines · schema ok",   icon: "pencil" },
    { idx: 7, role: "tool",      kind: "tool",    label: "validate(frontmatter)",                       meta: "pass · 0.0s",             icon: "cube" },
    { idx: 8, role: "assistant", kind: "judge",   label: "LLM-judge ensemble (3)",                      meta: "3 / 3 agree · pass",      icon: "scale" },
    { idx: 9, role: "tool",      kind: "verdict", label: "Scorer chain: pass",                           meta: "pillars 5/5 → 89.2",      icon: "check-circle-2" },
  ],
};

export const CONNECTED_REPOS: RegistryRepo[] = [
  { id: "mock-1", repo: "github.com/example/agent-benchmarks-results", owner: "demo-operator", branch: "main",    runs: 412, last_synced: "2 min ago",  status: "ok" },
  { id: "mock-2", repo: "github.com/rachel-yeh/ab-runs",                owner: "rachel-yeh",  branch: "main",    runs: 188, last_synced: "14 min ago", status: "ok" },
  { id: "mock-3", repo: "github.com/noamb/agent-bench-results",         owner: "noamb",       branch: "main",    runs: 96,  last_synced: "1 hr ago",   status: "ok" },
  { id: "mock-4", repo: "github.com/djun-kim/agent-bench",              owner: "djun-kim",    branch: "main",    runs: 71,  last_synced: "3 hr ago",   status: "ok" },
  { id: "mock-5", repo: "github.com/kpyrne/ab-eval",                    owner: "kpyrne",      branch: "main",    runs: 42,  last_synced: "9 hr ago",   status: "pending" },
  { id: "mock-6", repo: "github.com/ssaroliya/personal-bench",          owner: "ssaroliya",   branch: "develop", runs: 31,  last_synced: "2d ago",     status: "failed",  error: "malformed trajectory @ run-018" },
];

export const REGRESSIONS: RegressionItem[] = [
  { model: "gemini-2.5-pro",  suite: "L1_memory_write",  operator: "demo-operator",     delta_pct: -7.2, window_days: 14, prev_run_id: "ab-2026-13-04", current_run_id: "ab-2026-21-04" },
  { model: "o3",              suite: "L2_mcp",            operator: "rachel-yeh",  delta_pct: -5.4, window_days: 9,  prev_run_id: "ab-2026-15-02", current_run_id: "ab-2026-21-02" },
  { model: "claude-opus-4-1", suite: "L1_consolidation",  operator: "demo-operator",     delta_pct: -3.9, window_days: 7,  prev_run_id: "ab-2026-14-08", current_run_id: "ab-2026-21-04" },
];

export const IMPROVEMENTS: RegressionItem[] = [
  { model: "glm-4-6",           suite: "L0_smoke",      operator: "noamb",     delta_pct: +5.8, window_days: 7,  prev_run_id: "ab-2026-14-09", current_run_id: "ab-2026-21-04" },
  { model: "minimax-m2",        suite: "L1_retrieval",  operator: "demo-operator",   delta_pct: +4.1, window_days: 14, prev_run_id: "ab-2026-13-04", current_run_id: "ab-2026-19-05" },
  { model: "claude-sonnet-4-5", suite: "L3_skills",     operator: "djun-kim",  delta_pct: +3.6, window_days: 7,  prev_run_id: "ab-2026-14-08", current_run_id: "ab-2026-21-03" },
];

export const ALERT_RULES: AlertRule[] = [
  { name: "Memory suite drop",     condition: "L1_memory_write correctness ▼ > 5% over 7d", target: "any model", actions: ["email", "webhook"], status: "fired", last_fired_relative: "2h ago" },
  { name: "Cost regression",       condition: "$/sweep ▲ > 25% over 7d",                    target: "any model", actions: ["email"],            status: "idle"  },
  { name: "Smoke CI breaker",      condition: "L0_smoke pass-rate < 95%",                   target: "all models", actions: ["ci-block"],         status: "idle"  },
  { name: "Variance creep",        condition: "rerun σ > 4% over 14d",                      target: "any model", actions: ["email"],            status: "fired", last_fired_relative: "1d ago" },
];

export const SCRUBBER_FINDS: ScrubberFinding[] = [
  { line: 12, kind: "vault path",  match: "/Users/<placeholder>/vault/decisions/db-choice.md", severity: "med" },
  { line: 17, kind: "vault path",  match: "/Users/<placeholder>/vault/templates/decision.md",  severity: "med" },
  { line: 31, kind: "account ref", match: "decided_by: Demo Operator",                           severity: "low" },
];

export const SCRUBBER_RULES: ScrubberRule[] = [
  { name: "Vault absolute paths", pattern: "/Users/[^/]+/vault/",   replacement: "<vault>/" },
  { name: "Account references",   pattern: "decided_by:\\s*\\w+",   replacement: "decided_by: <user>" },
  { name: "API keys (env-style)", pattern: "[A-Z]+_API_KEY=\\S+",   replacement: "<REDACTED>" },
  { name: "Email addresses",      pattern: "\\S+@\\S+\\.\\w+",      replacement: "<email>" },
];

/* ─── Aggregate helpers consumed by header strip ──────────────────────────── */

export function totalRunsInWindow(): number {
  return LEADERBOARD.reduce((acc, r) => acc + r.runs, 0);
}
export function totalCostInWindow(): number {
  return LEADERBOARD.reduce((acc, r) => acc + r.sweep_cost * r.runs * 0.1, 0);
}
export function meanCorrectness(): number {
  return LEADERBOARD.reduce((acc, r) => acc + (r.scores[0] ?? 0), 0) / LEADERBOARD.length;
}
