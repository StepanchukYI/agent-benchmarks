/**
 * Domain types — mirror `packages/ab-datasets/ab_datasets/schemas/` Pydantic
 * models. Field names are snake_case to match `docs/schemas/*.schema.json` so
 * the frontend can consume `ab-server` JSON responses directly.
 *
 * Source of truth: the schemas in `docs/schemas/`. Update there first, then
 * here.
 */

export type Layer = "L0" | "L1" | "L2" | "L3" | "L4" | "L5";
export type Tier = "T0" | "T1" | "T2" | "T3";
export type TrustTier = "self_reported" | "verified" | "official";
export type Difficulty = "easy" | "medium" | "hard";
export type Visibility = "public" | "private";

export type ScorerKind =
  | "deterministic"
  | "llm_judge"
  | "state_diff"
  | "schema"
  | "exec"
  | "privacy_check";

export type RunStatus = "completed" | "timeout" | "unrunnable" | "error" | "running";

export interface ScorerSpec {
  name: string;
  kind: ScorerKind;
  config?: Record<string, unknown>;
}

export interface ScorerVerdict {
  scorer_name: string;
  kind: ScorerKind;
  pass: boolean;
  score: number;
  detail?: string;
}

export interface TaskConfig {
  required_tier: Tier;
  recommended_tier: Tier;
  also_run_on?: string[];
  requires?: Record<string, unknown>;
}

export interface Task {
  id: string;
  layer: Layer;
  suite: string;
  title: string;
  description: string;
  difficulty?: Difficulty;
  fixture_ref?: string | null;
  scorer_chain?: ScorerSpec[];
  acceptance_criteria?: string[];
  tags?: string[];
  visibility?: Visibility;
  trust_tier_ceiling?: TrustTier;
  config: TaskConfig;
  /** UI-only convenience — pass-rate over last 30d, 0-100. */
  pass_rate?: number;
}

export interface Suite {
  id: string;
  layer: Layer;
  name: string;
  description: string;
  task_count: number;
}

export type Vendor = "anthropic" | "openai" | "google" | "zhipu" | "minimax";

export interface Model {
  /** Pinned id, e.g. "claude-sonnet-4-5". */
  id: string;
  /** Short display name, e.g. "Sonnet 4.5". */
  short: string;
  vendor: Vendor;
  harness: string;
  capabilities: string[];
  /** USD per 1k input tokens. */
  cost_per_1k_in: number;
  /** USD per 1k output tokens. */
  cost_per_1k_out: number;
}

export interface Operator {
  handle: string;
  name: string;
  initials: string;
  /** Tailwind-resolvable hex for avatar background. UI-only. */
  color: string;
  /** github.com/<handle>/<repo>. */
  repo: string;
  trust_default: TrustTier;
  is_self?: boolean;
}

export interface DatasetPin {
  version: string;
  behind: number;
}

export interface LeaderboardRow {
  /** Model id. */
  model: string;
  /** Operator handle. */
  operator: string;
  trust_tier: TrustTier;
  source_commit_sha: string;
  /** Score per pillar, indexed by PILLARS array. */
  scores: number[];
  /** Δ vs previous 7d, per pillar. */
  delta: number[];
  runs: number;
  /** Standard deviation across reruns, percentage points. */
  variance: number;
  /** USD per task median. */
  cost_per_task: number;
  /** Median wall-clock latency in seconds. */
  latency_s: number;
  /** USD for a full L0+L1 sweep. */
  sweep_cost: number;
  dataset_pin: DatasetPin;
  tier: Tier;
}

export interface RunSummary {
  run_id: string;
  suite: string;
  model_count: number;
  status: RunStatus;
  started_at: string;
  duration_min: number;
  cost_usd: number;
  /** Mean correctness across tasks, 0-100. */
  score: number;
  /** Δ vs previous of same suite. */
  delta: number;
}

export interface TurnEvent {
  idx: number;
  role: "system" | "user" | "assistant" | "tool";
  kind:
    | "prompt"
    | "tool"
    | "read"
    | "write"
    | "thought"
    | "judge"
    | "verdict";
  label: string;
  meta: string;
  /** Lucide icon name. */
  icon: "cube" | "file-text" | "pencil" | "brain" | "scale" | "check-circle-2" | "user";
}

export interface Trajectory {
  task: Task;
  model: Model;
  operator: string;
  run_id: string;
  source_repo: string;
  source_commit_sha: string;
  tier: Tier;
  trust_tier: TrustTier;
  status: RunStatus;
  duration_s: number;
  cost_usd: number;
  tokens_in: number;
  tokens_out: number;
  pillar_scores: Record<string, number>;
  turns: TurnEvent[];
}

export interface RegistryRepo {
  repo: string;
  owner: string;
  branch: string;
  runs: number;
  last_synced: string;
  status: "ok" | "pending" | "failed";
  error?: string;
}

export interface RegressionItem {
  model: string;
  suite: string;
  operator: string;
  delta_pct: number;
  window_days: number;
  prev_run_id: string;
  current_run_id: string;
}

export interface AlertRule {
  name: string;
  condition: string;
  target: string;
  actions: ("email" | "webhook" | "ci-block")[];
  status: "idle" | "fired" | "muted";
  last_fired_relative?: string;
}

export interface ScrubberFinding {
  line: number;
  kind: string;
  match: string;
  severity: "low" | "med" | "high";
}

export interface ScrubberRule {
  name: string;
  pattern: string;
  replacement: string;
}
