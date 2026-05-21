import { LEADERBOARD, MODELS, SUITES } from "../../lib/mock-data";
import { ModelCell } from "../domain/ModelCell";

function score(modelIdx: number, suiteIdx: number): number {
  const base = LEADERBOARD[modelIdx]!.scores[0]!;
  const s = ((modelIdx * 7 + suiteIdx * 13) % 19) / 19;
  return Math.max(40, Math.min(98, base - 8 + s * 16));
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

/** model × suite correctness heatmap. */
export function ScoreHeatmap(): JSX.Element {
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-[11.5px]">
        <thead>
          <tr>
            <th className="text-left font-medium text-muted-foreground pl-3.5 py-2 sticky left-0 bg-panel border-b border-border">
              Model
            </th>
            {SUITES.map((s) => (
              <th key={s.id} className="text-right font-medium px-2 py-2 border-b border-border min-w-[80px]">
                <div className="font-mono text-[10px] text-muted-foreground">{s.layer}</div>
                <div className="font-medium text-foreground-2">{s.name}</div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {LEADERBOARD.map((r, mi) => {
            const m = MODELS.find((x) => x.id === r.model)!;
            return (
              <tr key={r.model}>
                <td className="pl-3.5 py-1.5 border-b border-border-soft">
                  <ModelCell model={m} />
                </td>
                {SUITES.map((s, si) => {
                  const v = score(mi, si);
                  return (
                    <td key={s.id} className="p-1 border-b border-border-soft">
                      <div
                        className="h-8 rounded-md grid place-items-center font-semibold tnum"
                        style={{ background: cellBg(v), color: cellFg(v) }}
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
