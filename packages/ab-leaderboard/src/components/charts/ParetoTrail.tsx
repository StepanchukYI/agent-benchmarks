import { useModels, useParetoHistory } from "../../api/hooks";
import type { ParetoHistorySeries } from "../../api/hooks";
import { toState } from "../../lib/ui-state";
import { EmptyState } from "../ui/EmptyState";
import { ErrorBanner } from "../ui/ErrorBanner";
import { LoadingSkeleton } from "../ui/LoadingSkeleton";

const VENDOR_HEX: Record<string, string> = {
  anthropic: "#d97757",
  openai: "#10a37f",
  google: "#4285f4",
  zhipu: "#8b5cf6",
  minimax: "#f59e0b",
};
const FALLBACK_HEX = "#94a3b8";

interface ParetoTrailProps {
  width?: number;
  height?: number;
  window?: "7d" | "30d" | "90d";
}

/** A series reduced to its plotted endpoints (latest point = "today"). */
interface PlottedSeries {
  key: string;
  model: string;
  short: string;
  color: string;
  points: { cost: number; score: number }[];
}

function niceMax(v: number, fallback: number): number {
  if (!Number.isFinite(v) || v <= 0) return fallback;
  return v;
}

/**
 * Cost-vs-correctness trails: each (model, tier) plotted across its real
 * weekly history (start → today) from GET /leaderboard/pareto/history. The
 * dashed envelope is the COMPUTED Pareto frontier over each series' latest
 * point (min cost / max score), not a decorative path.
 */
export function ParetoTrail({ width = 600, height = 280, window = "30d" }: ParetoTrailProps): JSX.Element {
  const historyQuery = useParetoHistory(window);
  const historyState = toState(
    historyQuery,
    (h: ParetoHistorySeries) =>
      h.series.length === 0 || h.series.every((s) => s.history.length === 0),
  );
  const { data: models } = useModels();
  const modelList = models ?? [];

  if (historyState.kind === "loading") {
    return <div className="p-2.5"><LoadingSkeleton rows={5} columns={1} /></div>;
  }
  if (historyState.kind === "error") {
    return (
      <div className="p-2.5">
        <ErrorBanner message={historyState.message} retry={() => historyQuery.refetch()} />
      </div>
    );
  }
  if (historyState.kind === "empty") {
    return (
      <div className="p-2.5">
        <EmptyState
          title="No cost/correctness history yet."
          hint="Trails appear once scored runs accumulate across at least one window."
        />
      </div>
    );
  }

  const series: PlottedSeries[] = historyState.value.series
    .filter((s) => s.history.length > 0)
    .map((s) => {
      const m = modelList.find((x) => x.id === s.model);
      return {
        key: `${s.model}::${s.tier}`,
        model: s.model,
        short: m?.short ?? s.model,
        color: m ? (VENDOR_HEX[m.vendor] ?? FALLBACK_HEX) : FALLBACK_HEX,
        // score_mean is the mean of score_total (0..1, weighted sum of pillar
        // verdicts). The pareto-history endpoint sends it raw — unlike the
        // leaderboard matrix query which pre-multiplies ×100 — so scale here
        // to the 0..100 the rest of the UI presents.
        points: s.history.map((p) => ({ cost: p.cost_usd_mean, score: p.score_mean * 100 })),
      };
    });

  // Dynamic domains from real data — no fixed 0..5 / 60..95 axes.
  const allPoints = series.flatMap((s) => s.points);
  const costMax = niceMax(Math.max(...allPoints.map((p) => p.cost)) * 1.1, 1);
  const scoreVals = allPoints.map((p) => p.score);
  const scoreLo = Math.min(...scoreVals);
  const scoreHi = Math.max(...scoreVals);
  // Pad the score axis; clamp to [0,100].
  const yMin = Math.max(0, Math.floor((scoreLo - 5) / 10) * 10);
  const yMax = Math.min(100, Math.ceil((scoreHi + 5) / 10) * 10) || 100;
  const xMin = 0;
  const xMax = costMax;

  const pad = { l: 40, r: 14, t: 14, b: 32 };
  const xPx = (v: number): number => pad.l + ((v - xMin) / (xMax - xMin || 1)) * (width - pad.l - pad.r);
  const yPx = (v: number): number => height - pad.b - ((v - yMin) / (yMax - yMin || 1)) * (height - pad.t - pad.b);

  // Computed Pareto frontier: over each series' latest point, keep the
  // non-dominated set (no other point has both lower cost AND higher score),
  // then draw it sorted by cost.
  const latest = series.map((s) => ({ ...s.points[s.points.length - 1]!, key: s.key }));
  const frontier = latest
    .filter((p) => !latest.some((q) => q.key !== p.key && q.cost <= p.cost && q.score >= p.score && (q.cost < p.cost || q.score > p.score)))
    .sort((a, b) => a.cost - b.cost);

  const yTicks = [yMin, yMin + (yMax - yMin) / 3, yMin + (2 * (yMax - yMin)) / 3, yMax].map((v) => Math.round(v));
  const xTicks = Array.from({ length: 6 }, (_, i) => (xMax / 5) * i);

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} className="block">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto">
          <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
        </marker>
      </defs>

      {yTicks.map((v) => (
        <g key={`y${v}`}>
          <line x1={pad.l} x2={width - pad.r} y1={yPx(v)} y2={yPx(v)} className="stroke-border-soft" strokeWidth="0.5" />
          <text x={pad.l - 8} y={yPx(v) + 3} textAnchor="end" fontSize="9.5" className="fill-muted-foreground">{v}</text>
        </g>
      ))}
      {xTicks.map((v, i) => (
        <text key={`x${i}`} x={xPx(v)} y={height - pad.b + 14} textAnchor="middle" fontSize="9.5" className="fill-muted-foreground">
          ${v.toFixed(v >= 1 ? 1 : 2)}
        </text>
      ))}
      <text x={pad.l - 30} y={pad.t + 6} fontSize="9" className="fill-muted-foreground">correctness</text>
      <text x={width - pad.r} y={height - 3} textAnchor="end" fontSize="9" className="fill-muted-foreground">cost / task ($)</text>

      {frontier.length >= 2 && (
        <>
          <path
            d={frontier.map((p, i) => `${i === 0 ? "M" : "L"}${xPx(p.cost)},${yPx(p.score)}`).join(" ")}
            className="stroke-border"
            strokeDasharray="3 3"
            strokeWidth="0.8"
            fill="none"
          />
          <text
            x={xPx(frontier[Math.floor(frontier.length / 2)]!.cost)}
            y={yPx(frontier[Math.floor(frontier.length / 2)]!.score) - 6}
            fontSize="9"
            className="fill-muted-foreground"
            fontStyle="italic"
          >
            pareto frontier
          </text>
        </>
      )}

      {series.map((s) => {
        const pts = s.points;
        const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${xPx(p.cost)},${yPx(p.score)}`).join(" ");
        const start = pts[0]!;
        const end = pts[pts.length - 1]!;
        return (
          <g key={s.key} style={{ color: s.color }}>
            <path d={path} stroke={s.color} strokeWidth="1" opacity={0.5} fill="none" markerEnd={pts.length > 1 ? "url(#arr)" : undefined} />
            {pts.length > 1 && <circle cx={xPx(start.cost)} cy={yPx(start.score)} r="2.5" fill={s.color} opacity="0.4" />}
            <circle cx={xPx(end.cost)} cy={yPx(end.score)} r="5" fill={s.color} opacity="0.22" />
            <circle cx={xPx(end.cost)} cy={yPx(end.score)} r="3" fill={s.color} />
            <text x={xPx(end.cost) + 8} y={yPx(end.score) + 3} fontSize="9.5" className="fill-foreground-2 font-mono">{s.short}</text>
          </g>
        );
      })}
    </svg>
  );
}
