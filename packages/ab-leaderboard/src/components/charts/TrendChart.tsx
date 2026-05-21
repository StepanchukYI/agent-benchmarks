import { MODELS, OPERATOR_TRENDS, OPERATORS, TRENDS } from "../../lib/mock-data";

interface TrendChartProps {
  showOperators?: boolean;
  width?: number;
  height?: number;
}

const VENDOR_HEX: Record<string, string> = {
  anthropic: "#d97757",
  openai: "#10a37f",
  google: "#4285f4",
  zhipu: "#8b5cf6",
  minimax: "#f59e0b",
};

const OP_COLORS = ["#ec4899", "#10b981", "#06b6d4", "#f59e0b", "#8b5cf6"];

export function TrendChart({ showOperators = false, width = 880, height = 280 }: TrendChartProps): JSX.Element {
  const pad = { l: 36, r: 16, t: 14, b: 28 };
  const days = 30;
  const xPx = (i: number): number => pad.l + (i / (days - 1)) * (width - pad.l - pad.r);
  const yMin = 55;
  const yMax = 95;
  const yPx = (v: number): number => height - pad.b - ((v - yMin) / (yMax - yMin)) * (height - pad.t - pad.b);

  const opLines = showOperators
    ? Object.entries(OPERATOR_TRENDS)
        .filter(([h]) => h !== "evgeniy")
        .map(([handle, data], i) => ({ handle, data, color: OP_COLORS[i % OP_COLORS.length]! }))
    : [];

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="block">
      {[60, 70, 80, 90].map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={width - pad.r} y1={yPx(v)} y2={yPx(v)} className="stroke-border-soft" strokeWidth="0.5" />
          <text x={pad.l - 8} y={yPx(v) + 3} textAnchor="end" fontSize="9.5" className="fill-muted-foreground">{v}</text>
        </g>
      ))}
      {[0, 7, 14, 21, 29].map((i) => (
        <g key={i}>
          <line x1={xPx(i)} x2={xPx(i)} y1={height - pad.b} y2={height - pad.b + 3} className="stroke-muted-foreground" strokeWidth="0.5" />
          <text x={xPx(i)} y={height - pad.b + 13} textAnchor="middle" fontSize="9.5" className="fill-muted-foreground">
            {i === 29 ? "today" : `-${29 - i}d`}
          </text>
        </g>
      ))}

      {/* Anomaly window callout */}
      <rect x={xPx(17)} y={pad.t} width={xPx(21) - xPx(17)} height={height - pad.t - pad.b} fill="hsl(var(--warn) / 0.10)" />
      <text x={(xPx(17) + xPx(21)) / 2} y={pad.t + 10} textAnchor="middle" fontSize="9" className="fill-warn">anomaly window</text>

      {MODELS.map((m) => {
        const data = TRENDS[m.id];
        if (!data) return null;
        const pts = data.map<[number, number]>((v, i) => [xPx(i), yPx(v)]);
        const d = pts.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
        const last = pts[pts.length - 1]!;
        const color = VENDOR_HEX[m.vendor];
        return (
          <g key={m.id}>
            <path d={d} stroke={color} strokeWidth="1.5" fill="none" opacity={0.85} />
            <circle cx={last[0]} cy={last[1]} r="3" fill={color} />
            <text x={last[0] - 6} y={last[1] - 6} textAnchor="end" fontSize="9.5" fill={color} className="font-mono">
              {m.short}
            </text>
          </g>
        );
      })}

      {opLines.map((s) => {
        const pts = s.data.map<[number, number]>((v, i) => [xPx(i), yPx(v)]);
        const d = pts.map((p, i) => (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1)).join(" ");
        const last = pts[pts.length - 1]!;
        return (
          <g key={s.handle}>
            <path d={d} stroke={s.color} strokeWidth="1.1" strokeDasharray="4 3" fill="none" opacity={0.7} />
            <circle cx={last[0]} cy={last[1]} r="2.5" fill={s.color} />
          </g>
        );
      })}
    </svg>
  );
}

export function trendLegendData(): { vendor: typeof MODELS[number]; color: string }[] {
  return MODELS.map((m) => ({ vendor: m, color: VENDOR_HEX[m.vendor]! }));
}

export function operatorLegendData(): { handle: string; color: string }[] {
  return OPERATORS.filter((o) => !o.is_self).slice(0, 5).map((o, i) => ({
    handle: o.handle,
    color: OP_COLORS[i % OP_COLORS.length]!,
  }));
}
