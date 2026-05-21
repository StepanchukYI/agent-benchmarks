import { useState } from "react";
import { AlertTriangle, Bell, Check, Clock, Network, TrendingUp } from "lucide-react";
import { SubNav } from "../components/shell/SubNav";
import { PageHero } from "../components/shell/PageHero";
import { StatStrip, type Stat } from "../components/shell/StatStrip";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { Button } from "../components/ui/Button";
import { Avatar } from "../components/ui/Avatar";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { LoadingSkeleton } from "../components/ui/LoadingSkeleton";
import { TrendChart, useOperatorLegendData, useTrendLegendData } from "../components/charts/TrendChart";
import { ParetoTrail } from "../components/charts/ParetoTrail";
import { ScoreHeatmap } from "../components/charts/ScoreHeatmap";
import { HotList } from "../components/trends/HotList";
import { AlertRulesPanel } from "../components/trends/AlertRulesPanel";
import { useOperators, useTrendsOverview, useTrendsRegressions } from "../api/hooks";
import { toState } from "../lib/ui-state";

type Range = "7d" | "30d" | "90d" | "custom";

export default function Trends(): JSX.Element {
  const [range, setRange] = useState<Range>("30d");
  const [showOperators, setShowOperators] = useState(false);
  const overviewQuery = useTrendsOverview();
  const regressionsQuery = useTrendsRegressions("down");
  const improvementsQuery = useTrendsRegressions("up");
  const operatorsQuery = useOperators();

  const overviewState = toState(overviewQuery, () => false);
  const regressionsState = toState(regressionsQuery);
  const improvementsState = toState(improvementsQuery);

  const trendLegend = useTrendLegendData();
  const operatorLegend = useOperatorLegendData();
  const regressions = regressionsState.kind === "ok" ? regressionsState.value : [];
  const improvements = improvementsState.kind === "ok" ? improvementsState.value : [];
  const operatorList = operatorsQuery.data ?? [];
  const overview = overviewState.kind === "ok" ? overviewState.value : null;

  const stats: Stat[] = [
    { label: <span className="inline-flex items-center gap-1.5"><AlertTriangle className="size-3 text-fail" /> Active regressions</span>, value: overview?.active_regressions ?? 0, unit: "P0", delta: "▲ 1 vs prev 30d", deltaValue: 1 },
    { label: <span className="inline-flex items-center gap-1.5"><TrendingUp className="size-3 text-pass" /> Improvements</span>, value: overview?.improvements ?? 0, unit: "tracked", delta: "▲ 2", deltaValue: 2 },
    { label: <span className="inline-flex items-center gap-1.5"><Check className="size-3 text-pass" /> CI gate</span>, value: overview?.ci_gate.status ?? "passing", unit: "last 48h", delta: `${overview?.ci_gate.blocked_merges ?? 0} blocked merges`, deltaValue: 0 },
    { label: <span className="inline-flex items-center gap-1.5"><Bell className="size-3" /> Alerts (30d)</span>, value: overview?.alerts_fired_30d ?? 0, unit: "fired", delta: "9 actioned", deltaValue: 0 },
    { label: <span className="inline-flex items-center gap-1.5"><Clock className="size-3" /> Last full sweep</span>, value: overview?.last_full_sweep_at ?? "", delta: "scheduled · 03:00 daily", deltaValue: 0 },
  ];

  const overviewMissing =
    overviewState.kind === "loading" ||
    overviewState.kind === "error" ||
    overview === null;

  return (
    <>
      <SubNav
        crumbs={[{ label: "Trends" }]}
        tabs={[
          { id: "overview", label: "Overview", active: true },
          { id: "suite", label: "By suite" },
          { id: "model", label: "By model" },
          { id: "alerts", label: "Alerts", count: 12 },
          { id: "ci", label: "CI gate" },
        ]}
      />

      <div className="flex-1 flex flex-col overflow-y-auto">
        <PageHero
          title="Trends & regressions"
          subtitle="Detect quality drift early. CI gate flags any P0 metric drop > 5%."
          actions={
            <>
              <div className="flex border border-border rounded-md overflow-hidden">
                {(["7d", "30d", "90d", "custom"] as Range[]).map((r) => (
                  <Button
                    key={r}
                    size="sm"
                    variant={range === r ? "primary" : "ghost"}
                    className="rounded-none border-0"
                    onClick={() => setRange(r)}
                  >
                    {r}
                  </Button>
                ))}
              </div>
              <Button>
                <Bell className="size-3" /> Alert rules
                <span className="ml-1 font-mono text-[10.5px] bg-panel-3 text-muted-foreground px-1 py-px rounded">2</span>
              </Button>
            </>
          }
        />

        {overviewState.kind === "error" && (
          <div className="px-5 pt-3">
            <ErrorBanner
              message={overviewState.message}
              retry={() => overviewQuery.refetch()}
            />
          </div>
        )}

        {overviewMissing && overviewState.kind === "loading" ? (
          <div className="px-5 pt-3"><LoadingSkeleton rows={1} columns={5} /></div>
        ) : (
          <StatStrip stats={stats} />
        )}

        {overviewState.kind === "empty" && (
          <div className="px-5 pt-3">
            <EmptyState
              title="Trends appear after at least 7 days of runs."
              hint="Keep submitting runs daily — drift detection kicks in once we have a baseline window."
            />
          </div>
        )}

        <div className="p-5 flex flex-col gap-3.5">
          <div className="grid gap-3.5" style={{ gridTemplateColumns: "1.7fr 1fr" }}>
            <Panel>
              <PanelHeader
                title={<>Correctness over time <span className="text-muted-foreground font-normal">· per model · 30d</span></>}
                actions={
                  <div className="flex items-center gap-2.5">
                    <Button
                      size="sm"
                      variant={showOperators ? "primary" : "default"}
                      onClick={() => setShowOperators((v) => !v)}
                    >
                      <Network className="size-3" /> Show friends
                      {showOperators && <span className="opacity-80 text-[10px] ml-0.5">· 5</span>}
                    </Button>
                    <div className="flex gap-2.5 text-[11px] text-muted-foreground">
                      {trendLegend.slice(0, 3).map((m) => (
                        <span key={m.vendor.id} className="inline-flex items-center gap-1.5">
                          <span className="size-2 rounded-full" style={{ background: m.color }} />
                          {m.vendor.short}
                        </span>
                      ))}
                      <span>+ {Math.max(trendLegend.length - 3, 0)} more</span>
                    </div>
                  </div>
                }
              />
              <div className="p-2.5">
                <TrendChart showOperators={showOperators} />
                {showOperators && (
                  <div className="px-3 py-2 pt-1 flex flex-wrap gap-3 text-[11px]">
                    <span className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Friends</span>
                    {operatorLegend.map(({ handle }) => {
                      const op = operatorList.find((o) => o.handle === handle);
                      if (!op) return null;
                      return (
                        <span key={handle} className="inline-flex items-center gap-1.5 text-foreground-2">
                          <Avatar operator={op} size={14} />
                          <span className="font-mono text-[11px]">@{handle}</span>
                        </span>
                      );
                    })}
                  </div>
                )}
              </div>
            </Panel>

            <div className="flex flex-col gap-3.5">
              <HotList
                kind="regression"
                items={regressions}
                state={regressionsState.kind}
                errorMessage={regressionsState.kind === "error" ? regressionsState.message : undefined}
                onRetry={() => regressionsQuery.refetch()}
              />
              <HotList
                kind="improvement"
                items={improvements}
                state={improvementsState.kind}
                errorMessage={improvementsState.kind === "error" ? improvementsState.message : undefined}
                onRetry={() => improvementsQuery.refetch()}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3.5">
            <Panel>
              <PanelHeader title="Cost vs. Correctness — trails" actions={<span className="text-[11px] text-muted-foreground">14d → today</span>} />
              <div className="p-2.5"><ParetoTrail /></div>
            </Panel>
            <AlertRulesPanel />
          </div>

          <Panel className="overflow-hidden">
            <PanelHeader
              title={<>Score heatmap <span className="text-muted-foreground font-normal">· models × suites</span></>}
              actions={
                <div className="flex gap-3 text-[11px] text-muted-foreground">
                  <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-fail" /> &lt; 60</span>
                  <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-warn" /> 60–80</span>
                  <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full bg-pass" /> &gt; 80</span>
                </div>
              }
            />
            <ScoreHeatmap />
          </Panel>
        </div>
      </div>
    </>
  );
}
