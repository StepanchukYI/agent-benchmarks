/**
 * Typed HTTP + URL builders for `ab-server` endpoints.
 *
 * Snake-case JSON matches the FastAPI server (which serves Pydantic models
 * directly). Field shapes here are mirrors of `src/lib/types.ts` so swapping
 * mock data for live data is a one-line change at the call site.
 *
 * Base URL is read from `import.meta.env.AB_API_BASE_URL`; defaults to
 * `http://localhost:8000/api/v1`.
 */

const DEFAULT_BASE_URL = "http://localhost:8000/api/v1";
const TOKEN_STORAGE_KEY = "ab.session_token";

function getBaseUrl(): string {
  return import.meta.env.AB_API_BASE_URL ?? DEFAULT_BASE_URL;
}

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (token === null) window.localStorage.removeItem(TOKEN_STORAGE_KEY);
    else window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // ignore — storage may be unavailable
  }
}

/** All endpoints, keyed by surface. Pure URL builders — no fetch coupling. */
export const endpoints = {
  /* ─── System ─── */
  version: () => "/version",

  /* ─── Auth ─── */
  authClientId: () => "/auth/github/client-id",
  authDeviceStart: () => "/auth/github/device-start",
  authDevicePoll: () => "/auth/github/device-poll",
  me: () => "/me",
  meVisibility: () => "/me/visibility",

  /* ─── Leaderboard ─── */
  leaderboard: (q?: {
    suites?: string[];
    models?: string[];
    operators?: string[];
    trust_tiers?: string[];
    dataset_current_only?: boolean;
    range?: "24h" | "7d" | "30d" | "90d";
    pillar?: "correctness" | "tool_skill" | "context_efficiency" | "latency_cost" | "memory_specific";
  }) => withQuery("/leaderboard", q),
  leaderboardPareto: () => "/leaderboard/pareto",
  /** Per-operator task drill: GET /leaderboard/row/tasks?model=&operator=&tier= */
  leaderboardRowTasks: (q: { model: string; operator: string; tier: string }) =>
    withQuery("/leaderboard/row/tasks", q),
  leaderboardHeatmap: (q?: { suites?: string[]; models?: string[]; tiers?: string[] }) =>
    withQuery("/leaderboard/heatmap", q),
  leaderboardParetoHistory: (q?: {
    window?: "7d" | "30d" | "90d";
    suites?: string[];
    tiers?: string[];
  }) => withQuery("/leaderboard/pareto/history", q),

  /* ─── Trends ─── */
  trends: (q?: { range?: "7d" | "30d" | "90d"; show_operators?: boolean }) =>
    withQuery("/trends/series", q),
  trendsOverview: () => "/trends/overview",
  trendsRegressions: (q?: { direction?: "down" | "up"; window_days?: number }) =>
    withQuery("/trends/regressions", q),
  trendsCiGate: () => "/trends/ci-gate",

  /* ─── Runs ─── */
  runsList: (q?: { status?: "scheduled" | "in_progress" | "recent"; limit?: number }) =>
    withQuery("/runs", q),
  runDetail: (id: string) => `/runs/${encodeURIComponent(id)}`,
  runEstimate: () => "/runs/estimate",
  runCreate: () => "/runs",
  runStreamSse: (id: string) => `/runs/${encodeURIComponent(id)}/stream`,
  runTrajectory: (runId: string, taskId: string) =>
    `/runs/${encodeURIComponent(runId)}/trajectories/${encodeURIComponent(taskId)}`,

  /* ─── Submissions ─── */
  submissionsList: () => "/submissions",
  submission: (id: string) => `/submissions/${encodeURIComponent(id)}`,
  submissionTrajectory: (id: string) => `/submissions/${encodeURIComponent(id)}/trajectory`,
  submissionPrivacyScan: (id: string) =>
    `/submissions/${encodeURIComponent(id)}/privacy-scan`,

  /* ─── Trajectories ─── */
  trajectoriesDefault: () => "/trajectories/default",

  /* ─── Tasks ─── */
  tasksList: () => "/tasks",
  taskDetail: (id: string) => `/tasks/${encodeURIComponent(id)}`,

  /* ─── Tiers ─── */
  tiersList: () => "/tiers",

  /* ─── Presets ─── */
  presetsList: () => "/presets",
  presetDetail: (id: string) => `/presets/${encodeURIComponent(id)}`,

  /* ─── Alerts ─── */
  alertsList: () => "/alerts",
  alertDetail: (id: string) => `/alerts/${encodeURIComponent(id)}`,
  alertCreate: () => "/alerts",
  alertUpdate: (id: string) => `/alerts/${encodeURIComponent(id)}`,
  alertDelete: (id: string) => `/alerts/${encodeURIComponent(id)}`,
  alertsEvaluate: () => "/alerts/evaluate",

  /* ─── Catalog ─── */
  operators: () => "/operators",
  models: () => "/models",

  /* ─── Account ─── */
  accountRepos: () => "/account/repos",
  accountPrivacyRules: () => "/account/privacy-rules",
  tokensList: () => "/account/tokens",
  tokenCreate: () => "/account/tokens",
  tokenDelete: (id: string) => `/account/tokens/${encodeURIComponent(id)}`,
} as const;

function withQuery(
  path: string,
  q?: Record<string, unknown>,
): string {
  if (!q) return path;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) {
    if (v == null) continue;
    if (Array.isArray(v)) v.forEach((x) => params.append(k, String(x)));
    else params.append(k, String(v));
  }
  const s = params.toString();
  return s ? `${path}?${s}` : path;
}

export async function apiFetch<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const base = getBaseUrl().replace(/\/$/, "");
  const suffix = path.startsWith("/") ? path : `/${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };
  const token = getStoredToken();
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  // Dev convenience: when AB_TEST_USER is set, send X-Test-User so
  // server's AB_TEST_AUTH=1 lets us call auth-gated endpoints without a real
  // GitHub OAuth flow. Never set this in production.
  const testUser = (import.meta.env as Record<string, string | undefined>)
    .AB_TEST_USER;
  if (testUser && !headers["X-Test-User"]) {
    headers["X-Test-User"] = testUser;
  }
  const response = await fetch(`${base}${suffix}`, { ...init, headers });
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText, suffix);
  }
  return (await response.json()) as T;
}

export class ApiError extends Error {
  status: number;
  url: string;
  constructor(status: number, statusText: string, url: string) {
    super(`API ${status} ${statusText} for ${url}`);
    this.status = status;
    this.url = url;
    this.name = "ApiError";
  }
}

/** Server-Sent Events helper for `/runs/{id}/stream`. */
export function openRunStream(id: string, onEvent: (e: MessageEvent) => void): EventSource {
  const base = getBaseUrl().replace(/\/$/, "");
  const url = `${base}${endpoints.runStreamSse(id)}`;
  const es = new EventSource(url);
  es.onmessage = onEvent;
  return es;
}
