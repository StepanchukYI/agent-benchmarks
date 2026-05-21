import { useState } from "react";
import { AlertTriangle, Bell, Check, Clock, Network, TrendingUp } from "lucide-react";
import { SubNav } from "../components/shell/SubNav";
import { PageHero } from "../components/shell/PageHero";
import { StatStrip, type Stat } from "../components/shell/StatStrip";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { Button } from "../components/ui/Button";
import { Avatar } from "../components/ui/Avatar";
import { TrendChart, operatorLegendData, trendLegendData } from "../components/charts/TrendChart";
import { ParetoTrail } from "../components/charts/ParetoTrail";
import { ScoreHeatmap } from "../components/charts/ScoreHeatmap";
import { HotList } from "../components/trends/HotList";
import { AlertRulesPanel } from "../components/trends/AlertRulesPanel";
import { IMPROVEMENTS, OPERATORS, REGRESSIONS } from "../lib/mock-data";

type Range = "7d" | "30d" | "90d" | "custom";

export default function Trends(): JSX.Element {
  const [range, setRange] = useState<Range>("30d");
  const [showOperators, setShowOperators] = useState(false);

  const stats: Stat[] = [
    { label: <span className="inline-flex items-center gap-1.5"><AlertTriangle className="size-3 text-fail" /> Active regressions</span>, value: 3, unit: "P0", delta: "▲ 1 vs prev 30d", deltaValue: 1 },
    { label: <span className="inline-flex items-center gap-1.5"><TrendingUp className="size-3 text-pass" /> Improvements</span>, value: 7, unit: "tracked", delta: "▲ 2", deltaValue: 2 },
    { label: <span className="inline-flex items-center gap-1.5"><Check className="size-3 text-pass" /> CI gate</span>, value: "passing", unit: "last 48h", delta: "0 blocked merges", deltaValue: 0 },
    { label: <span className="inline-flex items-center gap-1.5"><Bell className="size-3" /> Alerts (30d)</span>, value: 12, unit: "fired", delta: "9 actioned", deltaValue: 0 },
    { label: <span className="inline-flex items-center gap-1.5"><Clock className="size-3" /> Last full sweep</span>, value: "9h ago", delta: "scheduled · 03:00 daily", deltaValue: 0 },
  ];

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

        <StatStrip stats={stats} />

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
                      {trendLegendData().slice(0, 3).map((m) => (
                        <span key={m.vendor.id} className="inline-flex items-center gap-1.5">
                          <span className="size-2 rounded-full" style={{ background: m.color }} />
                          {m.vendor.short}
                        </span>
                      ))}
                      <span>+ {trendLegendData().length - 3} more</span>
                    </div>
                  </div>
                }
              />
              <div className="p-2.5">
                <TrendChart showOperators={showOperators} />
                {showOperators && (
                  <div className="px-3 py-2 pt-1 flex flex-wrap gap-3 text-[11px]">
                    <span className="text-[10.5px] uppercase tracking-wider text-muted-foreground">Friends</span>
                    {operatorLegendData().map(({ handle }) => {
                      const op = OPERATORS.find((o) => o.handle === handle)!;
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
              <HotList kind="regression" items={REGRESSIONS} />
              <HotList kind="improvement" items={IMPROVEMENTS} />
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
