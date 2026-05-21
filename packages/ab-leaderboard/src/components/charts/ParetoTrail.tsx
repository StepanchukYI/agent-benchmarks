import { LEADERBOARD, MODELS } from "../../lib/mock-data";

const VENDOR_HEX: Record<string, string> = {
  anthropic: "#d97757",
  openai: "#10a37f",
  google: "#4285f4",
  zhipu: "#8b5cf6",
  minimax: "#f59e0b",
};

interface ParetoTrailProps {
  width?: number;
  height?: number;
}

/**
 * Pareto with arrow trails: where each model was 14d ago → today. Lets the
 * viewer see whether a model improved (up-left) or regressed (down-right) on
 * the cost-correctness plane.
 */
export function ParetoTrail({ width = 600, height = 280 }: ParetoTrailProps): JSX.Element {
  const pad = { l: 40, r: 14, t: 14, b: 32 };
  const xMin = 0, xMax = 5;
  const yMin = 60, yMax = 95;
  const xPx = (v: number): number => pad.l + ((v - xMin) / (xMax - xMin)) * (width - pad.l - pad.r);
  const yPx = (v: number): number => height - pad.b - ((v - yMin) / (yMax - yMin)) * (height - pad.t - pad.b);

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="block">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
        </marker>
      </defs>

      {[60, 70, 80, 90].map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={width - pad.r} y1={yPx(v)} y2={yPx(v)} className="stroke-border-soft" strokeWidth="0.5" />
          <text x={pad.l - 8} y={yPx(v) + 3} textAnchor="end" fontSize="9.5" className="fill-muted-foreground">{v}</text>
        </g>
      ))}
      {[0, 1, 2, 3, 4, 5].map((v) => (
        <text key={v} x={xPx(v)} y={height - pad.b + 14} textAnchor="middle" fontSize="9.5" className="fill-muted-foreground">
          ${v}
        </text>
      ))}
      <text x={pad.l - 30} y={pad.t + 6} fontSize="9" className="fill-muted-foreground">correctness</text>
      <text x={width - pad.r} y={height - 3} textAnchor="end" fontSize="9" className="fill-muted-foreground">cost / sweep ($)</text>

      <path
        d="M40,180 L80,150 L160,100 L320,75 L460,55"
        className="stroke-border"
        strokeDasharray="3 3"
        strokeWidth="0.8"
        fill="none"
      />
      <text x="220" y="60" fontSize="9" className="fill-muted-foreground" fontStyle="italic">
        pareto frontier
      </text>

      {LEADERBOARD.map((r) => {
        const m = MODELS.find((x) => x.id === r.model);
        if (!m) return null;
        const color = VENDOR_HEX[m.vendor]!;
        const cost14 = r.sweep_cost * 1.18;
        const score14 = r.scores[0]! - (r.delta[0] ?? 0) * 4.2;
        const x0 = xPx(cost14), y0 = yPx(score14);
        const x1 = xPx(r.sweep_cost), y1 = yPx(r.scores[0]!);
        return (
          <g key={r.model} style={{ color }}>
            <line x1={x0} y1={y0} x2={x1} y2={y1} stroke={color} strokeWidth="1" opacity={0.5} markerEnd="url(#arr)" />
            <circle cx={x0} cy={y0} r="2.5" fill={color} opacity="0.4" />
            <circle cx={x1} cy={y1} r="5" fill={color} opacity="0.22" />
            <circle cx={x1} cy={y1} r="3" fill={color} />
            <text x={x1 + 8} y={y1 + 3} fontSize="9.5" className="fill-foreground-2 font-mono">{m.short}</text>
          </g>
        );
      })}
    </svg>
  );
}
