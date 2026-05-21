import { AlertTriangle, ChevronRight } from "lucide-react";
import { Panel, PanelHeader } from "../ui/Panel";
import { Button } from "../ui/Button";
import { ParetoChart } from "../charts/ParetoChart";
import { LEADERBOARD, MODELS, REGRESSIONS } from "../../lib/mock-data";
import { ModelCell } from "../domain/ModelCell";
import { cn } from "../../lib/utils";

export function RightRail(): JSX.Element {
  const topByCorrectness = [...LEADERBOARD].sort((a, b) => b.scores[0]! - a.scores[0]!).slice(0, 5);

  return (
    <aside className="w-[320px] shrink-0 border-l border-border-soft p-4 flex flex-col gap-3.5">
      <Panel>
        <PanelHeader title="Cost vs. Correctness" hint="L0 + L1 sweep" />
        <div className="p-2">
          <ParetoChart />
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Top 5 · Correctness" hint="7d" />
        <ul>
          {topByCorrectness.map((r, i) => {
            const m = MODELS.find((x) => x.id === r.model)!;
            const d = r.delta[0] ?? 0;
            return (
              <li key={r.model} className="flex items-center gap-2.5 px-3.5 py-2">
                <span className="w-3.5 text-muted-foreground text-[10.5px] tnum">{i + 1}</span>
                <ModelCell model={m} compact />
                <span className="flex-1" />
                <span className="font-semibold text-[12px] tnum">{r.scores[0]!.toFixed(1)}</span>
                <span className={cn("text-[10px] tnum", d > 0 ? "text-pass" : "text-fail")}>
                  {d > 0 ? "▲" : "▼"}{Math.abs(d).toFixed(1)}
                </span>
              </li>
            );
          })}
        </ul>
      </Panel>

      <Panel>
        <PanelHeader
          title={<span className="text-fail inline-flex items-center gap-1.5"><AlertTriangle className="size-3" /> Hot regressions</span>}
          hint="this week"
        />
        <ul>
          {REGRESSIONS.map((r, i) => (
            <li
              key={r.model + r.suite}
              className={cn("px-3.5 py-2.5", i > 0 && "border-t border-border-soft")}
            >
              <div className="font-mono text-[11px] font-medium">{r.model}</div>
              <div className="text-muted-foreground text-[10.5px] mt-0.5">
                {r.suite} · {r.window_days}d window
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-fail font-semibold text-[12px]">
                  ▼ {Math.abs(r.delta_pct).toFixed(1)}%
                </span>
                <Button size="sm" variant="ghost">Diff <ChevronRight className="size-3" /></Button>
              </div>
            </li>
          ))}
        </ul>
      </Panel>
    </aside>
  );
}
