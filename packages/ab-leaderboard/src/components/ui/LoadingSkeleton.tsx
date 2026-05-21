import { cn } from "../../lib/utils";

export interface LoadingSkeletonProps {
  /** Number of skeleton rows. Default 5. */
  rows?: number;
  /** Number of skeleton columns (cells per row). Default 4. */
  columns?: number;
  className?: string;
}

/**
 * Pulse skeleton used while react-query is `isPending`. Renders a
 * grid-shaped placeholder; for non-tabular surfaces, set `columns={1}`
 * to get a stacked list of bars.
 */
export function LoadingSkeleton({
  rows = 5,
  columns = 4,
  className,
}: LoadingSkeletonProps): JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={cn("flex flex-col gap-2 animate-pulse", className)}
    >
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          className="grid gap-2"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: columns }).map((_, c) => (
            <div
              key={c}
              className="h-4 rounded-md bg-panel-2 border border-border/60"
            />
          ))}
        </div>
      ))}
    </div>
  );
}
