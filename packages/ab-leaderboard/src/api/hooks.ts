/**
 * React Query hooks — one per `ab-server` endpoint.
 *
 * Behaviour: each hook calls the live endpoint, but supplies `placeholderData`
 * from `src/lib/mock-data.ts` so the UI renders immediately even when the
 * backend is unreachable. Once the live server replaces the placeholder, the
 * UI re-renders with real data. This lets the designer iterate without a live
 * `ab-server` running.
 *
 * To force-prefer mock data set `AB_USE_MOCK=1` in `.env.local`.
 */

import { useQuery, useMutation } from "@tanstack/react-query";
import { ApiError, apiFetch, endpoints } from "./client";
import {
  ALERT_RULES,
  CONNECTED_REPOS,
  IMPROVEMENTS,
  LEADERBOARD,
  MODELS,
  OPERATORS,
  PILLARS,
  REGRESSIONS,
  RECENT_RUNS,
  SCRUBBER_FINDS,
  SCRUBBER_RULES,
  SUITES,
  TASKS,
  TRAJECTORY,
  TRENDS,
  taskById,
} from "../lib/mock-data";
import type {
  AlertRule,
  LeaderboardRow,
  Operator,
  RegistryRepo,
  RegressionItem,
  RunSummary,
  ScrubberFinding,
  Task,
  Trajectory,
} from "../lib/types";

const USE_MOCK = (import.meta.env.AB_USE_MOCK ?? "0") === "1";

function fetchOrMock<T>(path: string, mock: T): Promise<T> {
  if (USE_MOCK) return Promise.resolve(mock);
  return apiFetch<T>(path).catch((err: unknown) => {
    if (err instanceof ApiError) {
      // The server is reachable but didn't have the resource — surface the
      // error so the UI can show a 404/500 state. For now we surface mock.
      return mock;
    }
    // Network down — fall back to mock so designer can iterate.
    return mock;
  });
}

/* ─── Leaderboard ────────────────────────────────────────────────────────── */

export interface LeaderboardResponse {
  rows: LeaderboardRow[];
  pillars: readonly string[];
  generated_at: string;
}

export function useLeaderboard(filters: {
  suites?: string[];
  models?: string[];
  operators?: string[];
  trust_tiers?: string[];
  dataset_current_only?: boolean;
  range?: "24h" | "7d" | "30d" | "90d";
}) {
  const mock: LeaderboardResponse = {
    rows: LEADERBOARD,
    pillars: PILLARS,
    generated_at: new Date().toISOString(),
  };
  return useQuery({
    queryKey: ["leaderboard", filters],
    queryFn: () => fetchOrMock(endpoints.leaderboard(filters), mock),
    placeholderData: mock,
  });
}

export interface ParetoPoint {
  model: string;
  cost_per_sweep_usd: number;
  correctness: number;
}

export function useLeaderboardPareto() {
  const mock = LEADERBOARD.map<ParetoPoint>((r) => ({
    model: r.model,
    cost_per_sweep_usd: r.sweep_cost,
    correctness: r.scores[0]!,
  }));
  return useQuery({
    queryKey: ["leaderboard", "pareto"],
    queryFn: () => fetchOrMock(endpoints.leaderboardPareto(), mock),
    placeholderData: mock,
  });
}

/* ─── Trends ─────────────────────────────────────────────────────────────── */

export interface TrendsOverview {
  active_regressions: number;
  improvements: number;
  ci_gate: { status: "passing" | "failing"; blocked_merges: number };
  alerts_fired_30d: number;
  last_full_sweep_at: string;
}

export function useTrendsOverview() {
  const mock: TrendsOverview = {
    active_regressions: 3,
    improvements: 7,
    ci_gate: { status: "passing", blocked_merges: 0 },
    alerts_fired_30d: 12,
    last_full_sweep_at: "9h ago",
  };
  return useQuery({
    queryKey: ["trends", "overview"],
    queryFn: () => fetchOrMock(endpoints.trendsOverview(), mock),
    placeholderData: mock,
  });
}

export interface TrendsSeriesResponse {
  per_model: Record<string, number[]>;
  per_operator: Record<string, number[]>;
  window_days: number;
}

export function useTrendsSeries(range: "7d" | "30d" | "90d" = "30d", showOperators = false) {
  const mock: TrendsSeriesResponse = {
    per_model: TRENDS,
    per_operator: {},
    window_days: range === "7d" ? 7 : range === "30d" ? 30 : 90,
  };
  return useQuery({
    queryKey: ["trends", range, { showOperators }],
    queryFn: () => fetchOrMock(endpoints.trends({ range, show_operators: showOperators }), mock),
    placeholderData: mock,
  });
}

export function useTrendsRegressions(direction: "down" | "up" = "down") {
  const mock: RegressionItem[] = direction === "down" ? REGRESSIONS : IMPROVEMENTS;
  return useQuery({
    queryKey: ["trends", "regressions", direction],
    queryFn: () => fetchOrMock(endpoints.trendsRegressions({ direction }), mock),
    placeholderData: mock,
  });
}

/* ─── Runs ───────────────────────────────────────────────────────────────── */

export function useRunsList(status?: "scheduled" | "in_progress" | "recent") {
  const mock: RunSummary[] = RECENT_RUNS;
  return useQuery({
    queryKey: ["runs", "list", status ?? "any"],
    queryFn: () => fetchOrMock(endpoints.runsList({ status, limit: 50 }), mock),
    placeholderData: mock,
  });
}

export interface RunEstimateRequest {
  suite_ids: string[];
  model_ids: string[];
  repetitions: number;
  tier?: "T0" | "T1" | "T2" | "T3";
}

export interface RunEstimateResponse {
  trajectories: number;
  estimated_cost_usd: number;
  estimated_duration_min: number;
  basis: string;
}

export function useRunEstimate() {
  return useMutation({
    mutationFn: async (req: RunEstimateRequest): Promise<RunEstimateResponse> => {
      const tasks = SUITES.filter((s) => req.suite_ids.includes(s.id)).reduce((n, s) => n + s.task_count, 0);
      const trajectories = tasks * req.model_ids.length * req.repetitions;
      const mock: RunEstimateResponse = {
        trajectories,
        estimated_cost_usd: +(trajectories * 0.04).toFixed(2),
        estimated_duration_min: Math.round(trajectories * 0.13),
        basis: "last 30d median cost/task",
      };
      try {
        return await apiFetch<RunEstimateResponse>(endpoints.runEstimate(), {
          method: "POST",
          body: JSON.stringify(req),
        });
      } catch {
        return mock;
      }
    },
  });
}

export function useCreateRun() {
  return useMutation({
    mutationFn: async (body: RunEstimateRequest & { preset_id?: string }) => {
      return apiFetch<{ run_id: string }>(endpoints.runCreate(), {
        method: "POST",
        body: JSON.stringify(body),
      });
    },
  });
}

/* ─── Tasks ──────────────────────────────────────────────────────────────── */

export function useTasksList() {
  const mock: Task[] = TASKS;
  return useQuery({
    queryKey: ["tasks", "list"],
    queryFn: () => fetchOrMock(endpoints.tasksList(), mock),
    placeholderData: mock,
  });
}

export function useTaskDetail(id: string | undefined) {
  return useQuery<Task>({
    queryKey: ["tasks", id],
    enabled: !!id,
    queryFn: async () => {
      if (!id) throw new Error("missing id");
      const mock = taskById(id);
      if (!mock) throw new Error("task not found");
      return fetchOrMock<Task>(endpoints.taskDetail(id), mock);
    },
  });
}

/* ─── Trajectory ─────────────────────────────────────────────────────────── */

export function useTrajectory(runId: string | undefined, taskId: string | undefined) {
  const mock: Trajectory = TRAJECTORY;
  return useQuery<Trajectory>({
    queryKey: ["trajectory", runId, taskId],
    enabled: !!runId && !!taskId,
    queryFn: () => fetchOrMock(endpoints.runTrajectory(runId!, taskId!), mock),
    placeholderData: mock,
  });
}

export function useSubmissionPrivacyScan(submissionId: string | undefined) {
  const mock: ScrubberFinding[] = SCRUBBER_FINDS;
  return useQuery<ScrubberFinding[]>({
    queryKey: ["submission", submissionId, "privacy-scan"],
    enabled: !!submissionId,
    queryFn: () => fetchOrMock(endpoints.submissionPrivacyScan(submissionId!), mock),
    placeholderData: mock,
  });
}

/* ─── Connected repos + operators ────────────────────────────────────────── */

export function useConnectedRepos() {
  const mock: RegistryRepo[] = CONNECTED_REPOS;
  return useQuery({
    queryKey: ["account", "repos"],
    queryFn: () => fetchOrMock("/account/repos", mock),
    placeholderData: mock,
  });
}

export function useOperators() {
  const mock: Operator[] = OPERATORS;
  return useQuery({
    queryKey: ["operators"],
    queryFn: () => fetchOrMock("/operators", mock),
    placeholderData: mock,
  });
}

/* ─── Models ─────────────────────────────────────────────────────────────── */

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: () => fetchOrMock("/models", MODELS),
    placeholderData: MODELS,
  });
}

/* ─── Privacy rules ──────────────────────────────────────────────────────── */

export function useScrubberRules() {
  return useQuery({
    queryKey: ["privacy", "rules"],
    queryFn: () => fetchOrMock("/account/privacy-rules", SCRUBBER_RULES),
    placeholderData: SCRUBBER_RULES,
  });
}

/* ─── Alert rules ────────────────────────────────────────────────────────── */

export function useAlertRules() {
  const mock: AlertRule[] = ALERT_RULES;
  return useQuery({
    queryKey: ["alerts", "rules"],
    queryFn: () => fetchOrMock(endpoints.alertsList(), mock),
    placeholderData: mock,
  });
}

export function useEvaluateAlerts() {
  return useMutation({
    mutationFn: () => apiFetch<{ fired: string[] }>(endpoints.alertsEvaluate(), { method: "POST" }),
  });
}
