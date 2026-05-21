import { useLeaderboard, useModels } from "../../api/hooks";

const VENDOR_HEX: Record<string, string> = {
  anthropic: "#d97757",
  openai: "#10a37f",
  google: "#4285f4",
  zhipu: "#8b5cf6",
  minimax: "#f59e0b",
};

interface ParetoChartProps {
  width?: number;
  height?: number;
}

/** Single snapshot — cost per sweep vs. correctness. */
export function ParetoChart({ width = 280, height = 180 }: ParetoChartProps): JSX.Element {
  const { data: leaderboard } = useLeaderboard({});
  const { data: models } = useModels();
  const rows = leaderboard?.rows ?? [];
  const modelList = models ?? [];
  const pad = { l: 36, r: 8, t: 8, b: 24 };
  const xs = rows.map((r) => r.sweep_cost);
  const ys = rows.map((r) => r.scores[0] ?? 0);
  const xMin = 0;
  const xMax = (xs.length > 0 ? Math.max(...xs) : 5) * 1.15;
  const yMin = 60;
  const yMax = 95;
  const xPx = (v: number): number => pad.l + ((v - xMin) / (xMax - xMin)) * (width - pad.l - pad.r);
  const yPx = (v: number): number => height - pad.b - ((v - yMin) / (yMax - yMin)) * (height - pad.t - pad.b);

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="block" aria-label="Cost vs correctness">
      {[0.25, 0.5, 0.75, 1].map((t) => (
        <line
          key={t}
          x1={pad.l}
          x2={width - pad.r}
          y1={pad.t + t * (height - pad.t - pad.b)}
          y2={pad.t + t * (height - pad.t - pad.b)}
          className="stroke-border-soft"
          strokeWidth="0.5"
        />
      ))}
      {[60, 70, 80, 90].map((v) => (
        <text key={v} x={pad.l - 6} y={yPx(v) + 3} textAnchor="end" fontSize="9" className="fill-muted-foreground">
          {v}
        </text>
      ))}
      {[0, 1, 2, 3, 4, 5].map((v) => (
        <text key={v} x={xPx(v)} y={height - pad.b + 12} textAnchor="middle" fontSize="9" className="fill-muted-foreground">
          ${v}
        </text>
      ))}
      <text x={pad.l} y={height - 3} fontSize="9" className="fill-muted-foreground">cost / sweep</text>

      {rows.map((r) => {
        const m = modelList.find((x) => x.id === r.model);
        if (!m) return null;
        const color = VENDOR_HEX[m.vendor];
        const y = r.scores[0] ?? 0;
        return (
          <g key={r.model}>
            <circle cx={xPx(r.sweep_cost)} cy={yPx(y)} r="5" fill={color} opacity="0.25" />
            <circle cx={xPx(r.sweep_cost)} cy={yPx(y)} r="3" fill={color} />
            <text x={xPx(r.sweep_cost) + 8} y={yPx(y) + 3} fontSize="9" className="fill-foreground-2 font-mono">
              {m.short}
            </text>
          </g>
        );
      })}
      {/* unused ys reference suppresses TS noUnusedLocals if we ever change axis bounds */}
      <desc>{`Models: ${ys.length}`}</desc>
    </svg>
  );
}
