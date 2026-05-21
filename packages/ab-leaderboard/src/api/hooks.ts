/**
 * React Query hooks — one per `ab-server` endpoint.
 *
 * Behaviour (post data-loading-honesty rewrite):
 *
 * - Hooks no longer set `placeholderData: mock`. The UI gets a real
 *   loading/empty/error state via `src/lib/ui-state.ts::toState`.
 * - `fetchOrMock` returns mock only in two cases:
 *     1. `AB_USE_MOCK=1` is set — always mock.
 *     2. The fetch fails at the network layer (TypeError raised by `fetch`,
 *        i.e. DNS / connection refused) AND we are in dev mode
 *        (`import.meta.env.DEV`). This preserves the "designer iterates
 *        without a live server" workflow.
 * - `ApiError` (any non-2xx HTTP code) is rethrown so react-query surfaces
 *   an `error` and the UI renders `ErrorBanner`.
 * - A successful 200 with an empty payload is returned as-is — consumers
 *   render `EmptyState`, not mock data.
 *
 * To force-prefer mock data set `AB_USE_MOCK=1` in `.env.local`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  ApiTokenCreated,
  ApiTokenSummary,
  LeaderboardRow,
  Operator,
  RegistryRepo,
  RegressionItem,
  RunSummary,
  ScrubberFinding,
  SubmissionSummary,
  Suite,
  Task,
  Trajectory,
} from "../lib/types";

const USE_MOCK = (import.meta.env.AB_USE_MOCK ?? "0") === "1";
/** Dev mode — used to decide whether to mock-fallback on network-level errors. */
const dev = import.meta.env.DEV === true;

/**
 * Fetch a live endpoint with controlled mock fallback semantics.
 *
 * - `AB_USE_MOCK=1` → always return `mock`.
 * - HTTP error (`ApiError`) → propagate so react-query renders error state.
 * - Network-layer failure (fetch throws non-`ApiError`, typically `TypeError`
 *   from DNS / connection refused):
 *     - in dev mode → fall back to `mock` so the designer can iterate.
 *     - in prod → propagate so the user sees an honest error.
 * - Successful 200 → return whatever the server sent (even if empty).
 */
function fetchOrMock<T>(path: string, mock: T): Promise<T> {
  if (USE_MOCK) return Promise.resolve(mock);
  return apiFetch<T>(path).catch((err: unknown) => {
    if (err instanceof ApiError) {
      // Real HTTP error from the server — let react-query surface it.
      throw err;
    }
    // Network-level failure (TypeError, AbortError, etc).
    if (dev) return mock;
    throw err;
  });
}

/**
 * When `AB_USE_MOCK=1`, seed react-query with `initialData` so the query
 * resolves synchronously to mock on the first render. This keeps the
 * "designer iterates without a server" workflow snappy AND lets the test
 * suite render data-rich pages without `await waitFor`.
 *
 * When `AB_USE_MOCK` is unset, returns `undefined` so the query starts in
 * `isPending` and the UI shows a real loading state.
 */
function mockSeed<T>(mock: T): { initialData: T } | Record<string, never> {
  return USE_MOCK ? { initialData: mock } : {};
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
  pillar?: "correctness" | "tool_skill" | "context_efficiency" | "latency_cost" | "memory_specific";
}) {
  const mock: LeaderboardResponse = {
    rows: LEADERBOARD,
    pillars: PILLARS,
    generated_at: new Date().toISOString(),
  };
  return useQuery({
    queryKey: ["leaderboard", filters],
    queryFn: () => fetchOrMock(endpoints.leaderboard(filters), mock),
    ...mockSeed(mock),
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
    ...mockSeed(mock),
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

interface TrendsOverviewServer {
  active_regressions_count?: number;
  improvements_count?: number;
  ci_gate_status?: "passing" | "failing";
  ci_gate_blocked_merges_48h?: number;
  alerts_count_window?: number;
  last_full_sweep_at?: string | null;
}

function normalizeTrendsOverview(
  resp: TrendsOverview | TrendsOverviewServer,
): TrendsOverview {
  if ("ci_gate" in resp && resp.ci_gate) return resp as TrendsOverview;
  const s = resp as TrendsOverviewServer;
  return {
    active_regressions: s.active_regressions_count ?? 0,
    improvements: s.improvements_count ?? 0,
    ci_gate: {
      status: s.ci_gate_status ?? "passing",
      blocked_merges: s.ci_gate_blocked_merges_48h ?? 0,
    },
    alerts_fired_30d: s.alerts_count_window ?? 0,
    last_full_sweep_at: s.last_full_sweep_at ?? "",
  };
}

export function useTrendsOverview() {
  const mock: TrendsOverview = {
    active_regressions: 3,
    improvements: 7,
    ci_gate: { status: "passing", blocked_merges: 0 },
    alerts_fired_30d: 12,
    last_full_sweep_at: "9h ago",
  };
  return useQuery<TrendsOverview>({
    queryKey: ["trends", "overview"],
    queryFn: async () => {
      const resp = await fetchOrMock<TrendsOverview | TrendsOverviewServer>(
        endpoints.trendsOverview(),
        mock,
      );
      return normalizeTrendsOverview(resp);
    },
    ...mockSeed(mock),
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
    ...mockSeed(mock),
  });
}

export function useTrendsRegressions(direction: "down" | "up" = "down") {
  const mock: RegressionItem[] = direction === "down" ? REGRESSIONS : IMPROVEMENTS;
  return useQuery({
    queryKey: ["trends", "regressions", direction],
    queryFn: async () => {
      // Server returns `{ direction, window_days, items: RegressionItem[] }`;
      // mock fixture is the bare array. Normalise both to RegressionItem[]
      // so the consumer (RightRail) can always .map() safely.
      const resp = await fetchOrMock<
        RegressionItem[] | { items: RegressionItem[] }
      >(endpoints.trendsRegressions({ direction }), mock);
      if (Array.isArray(resp)) return resp;
      return (resp?.items ?? []) as RegressionItem[];
    },
    ...mockSeed(mock),
  });
}

/* ─── Runs ───────────────────────────────────────────────────────────────── */

export function useRunsList(status?: "scheduled" | "in_progress" | "recent") {
  const mock: RunSummary[] = RECENT_RUNS;
  return useQuery<RunSummary[]>({
    queryKey: ["runs", "list", status ?? "any"],
    queryFn: async () => {
      const resp = await fetchOrMock<
        RunSummary[] | { items: RunSummary[] }
      >(endpoints.runsList({ status, limit: 50 }), mock);
      if (Array.isArray(resp)) return resp;
      return (resp?.items ?? []) as RunSummary[];
    },
    ...mockSeed(mock),
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
      } catch (err) {
        if (err instanceof ApiError) throw err;
        if (dev) return mock;
        throw err;
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
  return useQuery<Task[]>({
    queryKey: ["tasks", "list"],
    queryFn: async () => {
      const resp = await fetchOrMock<Task[] | { items: Task[] }>(
        endpoints.tasksList(),
        mock,
      );
      if (Array.isArray(resp)) return resp;
      return (resp?.items ?? []) as Task[];
    },
    ...mockSeed(mock),
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
    ...mockSeed(mock),
  });
}

/**
 * Lists public submissions from `GET /submissions`. Server wraps rows in
 * `{ items, limit, offset, count }`; we unwrap to a bare array for callers.
 * Empty array is the honest empty-state; no mock fallback in prod.
 */
export function useSubmissionsList() {
  const mock: SubmissionSummary[] = [];
  return useQuery<SubmissionSummary[]>({
    queryKey: ["submissions", "list"],
    queryFn: async () => {
      const resp = await fetchOrMock<
        SubmissionSummary[] | { items: SubmissionSummary[] }
      >(endpoints.submissionsList(), mock);
      if (Array.isArray(resp)) return resp;
      return (resp?.items ?? []) as SubmissionSummary[];
    },
    ...mockSeed(mock),
  });
}

export function useSubmissionPrivacyScan(submissionId: string | undefined) {
  const mock: ScrubberFinding[] = SCRUBBER_FINDS;
  return useQuery<ScrubberFinding[]>({
    queryKey: ["submission", submissionId, "privacy-scan"],
    enabled: !!submissionId,
    queryFn: () => fetchOrMock(endpoints.submissionPrivacyScan(submissionId!), mock),
    ...mockSeed(mock),
  });
}

/* ─── Connected repos + operators ────────────────────────────────────────── */

export function useConnectedRepos() {
  const mock: RegistryRepo[] = CONNECTED_REPOS;
  return useQuery({
    queryKey: ["account", "repos"],
    queryFn: () => fetchOrMock("/account/repos", mock),
    ...mockSeed(mock),
  });
}

export function useRegisterRepo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { repo_url: string; default_branch?: string; is_public?: boolean }) =>
      apiFetch("/repos", {
        method: "POST",
        body: JSON.stringify({
          repo_url: body.repo_url,
          default_branch: body.default_branch ?? "main",
          is_public: body.is_public ?? true,
        }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["account", "repos"] }),
  });
}

export function useSyncRepo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (repoId: string) =>
      apiFetch(`/repos/${encodeURIComponent(repoId)}/sync?inline=true`, {
        method: "POST",
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["account", "repos"] }),
  });
}

export function useDeleteRepo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (repoId: string) =>
      apiFetch(`/repos/${encodeURIComponent(repoId)}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["account", "repos"] }),
  });
}

/* ─── API tokens ─────────────────────────────────────────────────────────── */

export function useTokensList() {
  const mock: ApiTokenSummary[] = [];
  return useQuery<ApiTokenSummary[]>({
    queryKey: ["tokens"],
    queryFn: () => fetchOrMock(endpoints.tokensList(), mock),
    ...mockSeed(mock),
  });
}

export function useCreateToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string }) =>
      apiFetch<ApiTokenCreated>(endpoints.tokenCreate(), {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tokens"] }),
  });
}

export function useRevokeToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(endpoints.tokenDelete(id), { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tokens"] }),
  });
}

export function useOperators() {
  const mock: Operator[] = OPERATORS;
  return useQuery({
    queryKey: ["operators"],
    queryFn: () => fetchOrMock("/operators", mock),
    ...mockSeed(mock),
  });
}

/* ─── Models ─────────────────────────────────────────────────────────────── */

export function useModels() {
  return useQuery({
    queryKey: ["models"],
    queryFn: () => fetchOrMock("/models", MODELS),
    ...mockSeed(MODELS),
  });
}

/* ─── Privacy rules ──────────────────────────────────────────────────────── */

export function useScrubberRules() {
  return useQuery({
    queryKey: ["privacy", "rules"],
    queryFn: () => fetchOrMock("/account/privacy-rules", SCRUBBER_RULES),
    ...mockSeed(SCRUBBER_RULES),
  });
}

/* ─── Alert rules ────────────────────────────────────────────────────────── */

export function useAlertRules() {
  const mock: AlertRule[] = ALERT_RULES;
  return useQuery({
    queryKey: ["alerts", "rules"],
    queryFn: () => fetchOrMock(endpoints.alertsList(), mock),
    ...mockSeed(mock),
  });
}

export function useEvaluateAlerts() {
  return useMutation({
    mutationFn: () => apiFetch<{ fired: string[] }>(endpoints.alertsEvaluate(), { method: "POST" }),
  });
}

export interface AlertCreateBody {
  name: string;
  metric?: string;
  suite?: string | null;
  model?: string | null;
  tier?: string | null;
  direction?: "down" | "up";
  threshold_pct?: number;
  window_days?: number;
  enabled?: boolean;
}

export function useCreateAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AlertCreateBody) =>
      apiFetch<Record<string, unknown>>(endpoints.alertCreate(), {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts", "rules"] }),
  });
}

export function useUpdateAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<AlertCreateBody> }) =>
      apiFetch<Record<string, unknown>>(endpoints.alertUpdate(id), {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts", "rules"] }),
  });
}

export function useDeleteAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch(endpoints.alertDelete(id), { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts", "rules"] }),
  });
}

/* ─── Trends CI gate ─────────────────────────────────────────────────────── */

export interface TrendsCiGate {
  status: string;
  blocked_merges_48h: number;
  threshold_pct: number;
  computed_at: string;
}

export function useTrendsCiGate() {
  const mock: TrendsCiGate = {
    status: "passing",
    blocked_merges_48h: 0,
    threshold_pct: 0.05,
    computed_at: new Date().toISOString(),
  };
  return useQuery<TrendsCiGate>({
    queryKey: ["trends", "ci-gate"],
    queryFn: () => fetchOrMock(endpoints.trendsCiGate(), mock),
    ...mockSeed(mock),
  });
}

/* ─── Suites ─────────────────────────────────────────────────────────────── */

export function useSuites() {
  const mock: Suite[] = SUITES;
  return useQuery({
    queryKey: ["suites"],
    queryFn: () => fetchOrMock("/suites", mock),
    ...mockSeed(mock),
  });
}

/* ─── Pillars (UI constants — server may serve these alongside leaderboard) ── */

export function usePillars() {
  const mock = PILLARS as readonly string[];
  return useQuery({
    queryKey: ["pillars"],
    queryFn: () => fetchOrMock<readonly string[]>("/pillars", mock),
    ...mockSeed(mock),
  });
}

/* ─── Trajectory placeholder (used by trajectory page chrome until server has runId/taskId) ── */

/**
 * Returns the current viewer's pinned trajectory. The viewer page renders even
 * without an explicit run/task selection — this is the "default" payload.
 */
export function useDefaultTrajectory() {
  const mock: Trajectory = TRAJECTORY;
  return useQuery<Trajectory>({
    queryKey: ["trajectory", "default"],
    queryFn: () => fetchOrMock("/trajectories/default", mock),
    ...mockSeed(mock),
  });
}

/* ─── Auth (GitHub device flow + viewer identity) ────────────────────────── */

import { fetchMe, signOut as _signOut } from "./auth";
import type { MeResponse } from "./auth";

/**
 * Current authenticated viewer. Returns null when no token / token rejected.
 * Always refetches on mount so a fresh tab reflects a stale localStorage value.
 */
export function useMe() {
  return useQuery<MeResponse | null>({
    queryKey: ["auth", "me"],
    queryFn: fetchMe,
    staleTime: 30_000,
    retry: false,
  });
}

export function useSignOut() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      _signOut();
    },
    onSuccess: () => {
      qc.setQueryData(["auth", "me"], null);
      qc.invalidateQueries();
    },
  });
}

/**
 * Partial update of viewer visibility toggles (`public_profile`, `share_runs`).
 * Server returns the refreshed user; we seed it into the `["auth", "me"]`
 * cache so UI reflects the change without a refetch round-trip.
 */
export function useUpdateMeVisibility() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      public_profile?: boolean;
      share_runs?: boolean;
    }): Promise<MeResponse> =>
      apiFetch<MeResponse>(endpoints.meVisibility(), {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
    onSuccess: (data) => {
      qc.setQueryData(["auth", "me"], data);
    },
  });
}
