import { cn } from "../../lib/utils";
import type { TrajectoryViewTurn, TrajectoryViewHeaderTotals } from "../../lib/types";

interface CostLedgerProps {
  /** Per-turn cost/token data from the real trajectory. */
  turns: TrajectoryViewTurn[];
  /** Run totals (tokens, latency, cost) from the trajectory header. */
  totals: TrajectoryViewHeaderTotals | null;
}

export function CostLedger({ turns, totals }: CostLedgerProps): JSX.Element {
  if (!totals && turns.length === 0) {
    return (
      <div className="text-[11.5px] text-muted-foreground py-3 text-center">
        No cost data for this trajectory.
      </div>
    );
  }

  const tokensIn = totals?.tokens_in ?? turns.reduce((a, t) => a + t.tokens_in, 0);
  const tokensOut = totals?.tokens_out ?? turns.reduce((a, t) => a + t.tokens_out, 0);
  const total = totals?.cost_usd ?? turns.reduce((a, t) => a + t.cost_usd, 0);
  const latencyMs = totals?.latency_ms ?? turns.reduce((a, t) => a + t.latency_ms, 0);
  const max = turns.length ? Math.max(...turns.map((t) => t.cost_usd)) : 0;

  return (
    <div>
      {turns.length > 0 && (
        <div className="flex items-end gap-1 h-[60px] py-2 px-1">
          {turns.map((t) => (
            <div key={t.idx} className="flex-1 flex flex-col items-center gap-[3px]">
              <div
                title={`#${t.idx} · $${t.cost_usd.toFixed(4)}`}
                className={cn("w-full rounded-sm bg-accent/80")}
                style={{ height: Math.max(2, max > 0 ? (t.cost_usd / max) * 44 : 2) + "px" }}
              />
              <span className="font-mono text-[9px] text-muted-foreground">{t.idx}</span>
            </div>
          ))}
        </div>
      )}
      <div className="h-px bg-border-soft my-2" />
      <div className="grid grid-cols-2 gap-2 px-0.5">
        <Cell label="Tokens in" value={(tokensIn ?? 0).toLocaleString()} />
        <Cell label="Tokens out" value={(tokensOut ?? 0).toLocaleString()} />
        <Cell label="Total cost" value={"$" + (total ?? 0).toFixed(4)} accent />
        <Cell label="Wall clock" value={(latencyMs ?? 0) > 0 ? ((latencyMs ?? 0) / 1000).toFixed(1) + " s" : "—"} />
      </div>
    </div>
  );
}

function Cell({ label, value, accent }: { label: string; value: string; accent?: boolean }): JSX.Element {
  return (
    <div>
      <div className="text-[10.5px] text-muted-foreground">{label}</div>
      <div className={cn("font-mono tnum font-medium text-[13px]", accent && "text-accent")}>
        {value}
      </div>
    </div>
  );
}
