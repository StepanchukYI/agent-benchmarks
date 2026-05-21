import { MODELS, OPERATORS } from "../../lib/mock-data";
import { useModels, useOperators, useTrendsSeries } from "../../api/hooks";
import type { Model } from "../../lib/types";

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
  const { data: models } = useModels();
  const { data: trendsSeries } = useTrendsSeries("30d", showOperators);
  const modelList: Model[] = models ?? [];
  // Series values can be null for days with no runs (gaps). Keep null in the
  // working type so we can break the polyline instead of dropping to zero.
  const perModel: Record<string, (number | null)[]> = trendsSeries?.per_model ?? {};
  const perOperator: Record<string, (number | null)[]> = trendsSeries?.per_operator ?? {};
  const pad = { l: 36, r: 16, t: 14, b: 28 };
  const days = 30;
  const xPx = (i: number): number => pad.l + (i / (days - 1)) * (width - pad.l - pad.r);
  const yMin = 55;
  const yMax = 95;
  const yPx = (v: number): number => height - pad.b - ((v - yMin) / (yMax - yMin)) * (height - pad.t - pad.b);

  // Build an SVG path that breaks at null gaps (M starts a fresh segment
  // after every missing day) instead of interpolating through 0.
  const pathFromSeries = (data: (number | null)[]): string => {
    let d = "";
    let penDown = false;
    data.forEach((v, i) => {
      if (v == null) {
        penDown = false;
        return;
      }
      const cmd = penDown ? "L" : "M";
      d += `${cmd}${xPx(i).toFixed(1)},${yPx(v).toFixed(1)} `;
      penDown = true;
    });
    return d.trim();
  };

  // Last non-null point — for the end-of-line label/dot.
  const lastPoint = (data: (number | null)[]): [number, number] | null => {
    for (let i = data.length - 1; i >= 0; i--) {
      const v = data[i];
      if (v != null) return [xPx(i), yPx(v)];
    }
    return null;
  };

  const opLines = showOperators
    ? Object.entries(perOperator)
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

      {modelList.map((m) => {
        const data = perModel[m.id];
        if (!data) return null;
        const d = pathFromSeries(data);
        const last = lastPoint(data);
        if (!d || !last) return null;
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
        const d = pathFromSeries(s.data);
        const last = lastPoint(s.data);
        if (!d || !last) return null;
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

/**
 * Hook-driven legend data. Backed by `useModels`/`useOperators` — placeholder
 * data from mock-data means these return immediately on first render.
 */
export function useTrendLegendData(): { vendor: Model; color: string }[] {
  const { data: models } = useModels();
  return (models ?? MODELS).map((m) => ({ vendor: m, color: VENDOR_HEX[m.vendor]! }));
}

export function useOperatorLegendData(): { handle: string; color: string }[] {
  const { data: operators } = useOperators();
  return (operators ?? OPERATORS)
    .filter((o) => !o.is_self)
    .slice(0, 5)
    .map((o, i) => ({
      handle: o.handle,
      color: OP_COLORS[i % OP_COLORS.length]!,
    }));
}
