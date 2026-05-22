/**
 * Honest UI-state mapping for React Query results.
 *
 * Replaces the previous pattern of `placeholderData: mock` (which silently
 * masks an empty DB or a broken backend) with an explicit four-shape state
 * machine: loading | empty | ok | error. Consumers render `LoadingSkeleton`,
 * `EmptyState`, `ErrorBanner`, or the data view accordingly.
 */

import type { UseQueryResult } from "@tanstack/react-query";

export type DataState<T> =
  | { kind: "loading" }
  | { kind: "empty" }
  | { kind: "ok"; value: T }
  | { kind: "error"; message: string };

function defaultIsEmpty<T>(value: T): boolean {
  return Array.isArray(value) && value.length === 0;
}

/**
 * Map a `UseQueryResult` to a `DataState`.
 *
 * Order matters:
 *   1. `isPending` (no data yet, no error yet) → loading.
 *   2. `isError` → error (the live fetch raised; hooks decide whether to
 *       fall back to mock for network errors in dev — see `api/hooks.ts`).
 *   3. data is present but `isEmpty(value)` → empty.
 *   4. otherwise → ok.
 */
export function toState<T>(
  query: UseQueryResult<T>,
  isEmpty: (value: T) => boolean = defaultIsEmpty,
): DataState<T> {
  if (query.isPending) return { kind: "loading" };
  if (query.isError) {
    const err = query.error;
    const message =
      err instanceof Error ? err.message : "Request failed.";
    return { kind: "error", message };
  }
  const value = query.data as T;
  // undefined means react-query settled without a value (no success yet); treat as loading.
  // null means the queryFn explicitly returned null (e.g. 404 → "no data"); treat as empty.
  if (value === undefined) return { kind: "loading" };
  if (value === null) return { kind: "empty" };
  if (isEmpty(value)) return { kind: "empty" };
  return { kind: "ok", value };
}
