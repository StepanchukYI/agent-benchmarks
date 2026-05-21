import { cn } from "../../lib/utils";

interface CostLedgerProps {
  /** Per-turn cost. */
  turns?: TurnCost[];
}

interface TurnCost {
  idx: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

const DEFAULT_TURNS: TurnCost[] = [
  { idx: 1, tokens_in: 4210, tokens_out: 0,    cost_usd: 0.0126 },
  { idx: 2, tokens_in: 28,   tokens_out: 19,   cost_usd: 0.0001 },
  { idx: 3, tokens_in: 240,  tokens_out: 8,    cost_usd: 0.0008 },
  { idx: 4, tokens_in: 1240, tokens_out: 312,  cost_usd: 0.0084 },
  { idx: 5, tokens_in: 124,  tokens_out: 6,    cost_usd: 0.0004 },
  { idx: 6, tokens_in: 86,   tokens_out: 1402, cost_usd: 0.0213 },
  { idx: 7, tokens_in: 32,   tokens_out: 4,    cost_usd: 0.0001 },
  { idx: 8, tokens_in: 6520, tokens_out: 353,  cost_usd: 0.0249 },
  { idx: 9, tokens_in: 0,    tokens_out: 0,    cost_usd: 0.0182 },
];

export function CostLedger({ turns = DEFAULT_TURNS }: CostLedgerProps): JSX.Element {
  const total = turns.reduce((a, t) => a + t.cost_usd, 0);
  const tokensIn = turns.reduce((a, t) => a + t.tokens_in, 0);
  const tokensOut = turns.reduce((a, t) => a + t.tokens_out, 0);
  const max = Math.max(...turns.map((t) => t.cost_usd));

  return (
    <div>
      <div className="flex items-end gap-1 h-[60px] py-2 px-1">
        {turns.map((t) => (
          <div key={t.idx} className="flex-1 flex flex-col items-center gap-[3px]">
            <div
              title={`#${t.idx} · $${t.cost_usd.toFixed(4)}`}
              className={cn("w-full rounded-sm bg-accent/80")}
              style={{ height: Math.max(2, (t.cost_usd / max) * 44) + "px" }}
            />
            <span className="font-mono text-[9px] text-muted-foreground">{t.idx}</span>
          </div>
        ))}
      </div>
      <div className="h-px bg-border-soft my-2" />
      <div className="grid grid-cols-2 gap-2 px-0.5">
        <Cell label="Tokens in" value={tokensIn.toLocaleString()} />
        <Cell label="Tokens out" value={tokensOut.toLocaleString()} />
        <Cell label="Total cost" value={"$" + total.toFixed(4)} accent />
        <Cell label="Wall clock" value="18.4 s" />
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
