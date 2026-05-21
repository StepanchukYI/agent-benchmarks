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

function getBaseUrl(): string {
  return import.meta.env.AB_API_BASE_URL ?? DEFAULT_BASE_URL;
}

/** All endpoints, keyed by surface. Pure URL builders — no fetch coupling. */
export const endpoints = {
  /* ─── Leaderboard ─── */
  leaderboard: (q?: {
    suites?: string[];
    models?: string[];
    operators?: string[];
    trust_tiers?: string[];
    dataset_current_only?: boolean;
    range?: "24h" | "7d" | "30d" | "90d";
  }) => withQuery("/leaderboard", q),
  leaderboardPareto: () => "/leaderboard/pareto",

  /* ─── Trends ─── */
  trends: (q?: { range?: "7d" | "30d" | "90d"; show_operators?: boolean }) =>
    withQuery("/trends", q),
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
  submission: (id: string) => `/submissions/${encodeURIComponent(id)}`,
  submissionTrajectory: (id: string) => `/submissions/${encodeURIComponent(id)}/trajectory`,
  submissionPrivacyScan: (id: string) =>
    `/submissions/${encodeURIComponent(id)}/privacy-scan`,

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
  alertsEvaluate: () => "/alerts/evaluate",
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
  const response = await fetch(`${base}${suffix}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
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
