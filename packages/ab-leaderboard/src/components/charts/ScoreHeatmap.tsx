import { useHeatmap, useModels, useSuites } from "../../api/hooks";
import type { HeatmapResponse } from "../../api/hooks";
import type { Suite } from "../../lib/types";
import { toState } from "../../lib/ui-state";
import { ModelCell } from "../domain/ModelCell";
import { Tag } from "../ui/Tag";
import { EmptyState } from "../ui/EmptyState";
import { ErrorBanner } from "../ui/ErrorBanner";
import { LoadingSkeleton } from "../ui/LoadingSkeleton";

/** Render a 0..1 mean-correctness score as a 0..100 number. */
function asPct(score01: number): number {
  return score01 * 100;
}
function cellBg(v: number): string {
  const t = Math.max(0, Math.min(1, (v - 50) / 45));
  if (t > 0.85) return "hsl(var(--pass) / 0.32)";
  if (t > 0.7)  return "hsl(var(--pass) / 0.18)";
  if (t > 0.55) return "hsl(var(--warn) / 0.18)";
  if (t > 0.4)  return "hsl(var(--warn) / 0.28)";
  return "hsl(var(--fail) / 0.25)";
}
function cellFg(v: number): string {
  if (v < 60) return "hsl(var(--fail))";
  return "hsl(var(--foreground))";
}

/** model × suite mean-correctness heatmap, from GET /leaderboard/heatmap. */
export function ScoreHeatmap(): JSX.Element {
  const heatmapQuery = useHeatmap();
  const heatmapState = toState(
    heatmapQuery,
    (h: HeatmapResponse) => h.rows.length === 0,
  );
  const { data: models } = useModels();
  const { data: suites } = useSuites();
  const modelList = models ?? [];
  const suiteList = suites ?? [];

  if (heatmapState.kind === "loading") {
    return <div className="p-3.5"><LoadingSkeleton rows={5} columns={5} /></div>;
  }
  if (heatmapState.kind === "error") {
    return (
      <div className="p-3.5">
        <ErrorBanner message={heatmapState.message} retry={() => heatmapQuery.refetch()} />
      </div>
    );
  }
  if (heatmapState.kind === "empty") {
    return (
      <div className="p-3.5">
        <EmptyState
          title="No heatmap data yet."
          hint="Per-suite correctness appears once runs have been scored across models and suites."
        />
      </div>
    );
  }

  const heatmap = heatmapState.value;
  // Server returns suite ids; resolve to suite metadata (layer/name) when known,
  // else show the raw id.
  const suiteCols: { id: string; suite: Suite | undefined }[] = heatmap.suites.map(
    (id) => ({ id, suite: suiteList.find((s) => s.id === id) }),
  );

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[11.5px]">
        <thead>
          <tr>
            <th className="text-left font-medium text-muted-foreground pl-3.5 py-2 sticky left-0 bg-panel border-b border-border">
              Model
            </th>
            {suiteCols.map(({ id, suite }) => (
              <th key={id} className="text-right font-medium px-2 py-2 border-b border-border min-w-[80px]">
                <div className="font-mono text-[10px] text-muted-foreground">{suite?.layer ?? ""}</div>
                <div className="font-medium text-foreground-2">{suite?.name ?? id}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {heatmap.rows.map((r) => {
            const m = modelList.find((x) => x.id === r.model);
            return (
              <tr key={`${r.model}::${r.tier}`}>
                <td className="pl-3.5 py-1.5 border-b border-border-soft">
                  <div className="flex items-center gap-2">
                    {m ? <ModelCell model={m} /> : <span className="font-mono">{r.model}</span>}
                    <Tag>{r.tier}</Tag>
                  </div>
                </td>
                {suiteCols.map(({ id }) => {
                  const cell = r.cells[id];
                  const score01 = cell?.score_correctness ?? null;
                  if (score01 == null) {
                    return (
                      <td key={id} className="p-1 border-b border-border-soft">
                        <div className="h-8 rounded-md grid place-items-center text-muted-foreground/50">
                          —
                        </div>
                      </td>
                    );
                  }
                  const v = asPct(score01);
                  return (
                    <td key={id} className="p-1 border-b border-border-soft">
                      <div
                        className="h-8 rounded-md grid place-items-center font-semibold tnum"
                        style={{ background: cellBg(v), color: cellFg(v) }}
                        title={`n=${cell?.n ?? 0}`}
                      >
                        {v.toFixed(1)}
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
