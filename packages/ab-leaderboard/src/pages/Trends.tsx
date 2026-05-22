import { useState } from "react";
import { AlertTriangle, Bell, Check, Clock, Network, Plus, Trash2, TrendingUp } from "lucide-react";
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
import {
  useAlertRules,
  useCreateAlert,
  useDeleteAlert,
  useOperators,
  useTrendsCiGate,
  useTrendsOverview,
  useTrendsRegressions,
  useTrendsSeries,
} from "../api/hooks";
import { toState } from "../lib/ui-state";
import { deltaArrow } from "../lib/format";

type Range = "7d" | "30d" | "90d" | "custom";
type TrendsTab = "overview" | "by_suite" | "by_model" | "alerts" | "ci_gate";

export default function Trends(): JSX.Element {
  const [range, setRange] = useState<Range>("30d");
  const [activeTab, setActiveTab] = useState<TrendsTab>("overview");
  const [showOperators, setShowOperators] = useState(false);
  const overviewQuery = useTrendsOverview();
  const regressionsQuery = useTrendsRegressions("down");
  const improvementsQuery = useTrendsRegressions("up");
  const operatorsQuery = useOperators();
  const alertRulesQuery = useAlertRules();
  const alertCount = alertRulesQuery.data?.length;

  const overviewState = toState(overviewQuery, () => false);
  const regressionsState = toState(regressionsQuery);
  const improvementsState = toState(improvementsQuery);

  const trendLegend = useTrendLegendData();
  const operatorLegend = useOperatorLegendData();
  const regressions = regressionsState.kind === "ok" ? regressionsState.value : [];
  const improvements = improvementsState.kind === "ok" ? improvementsState.value : [];
  const operatorList = operatorsQuery.data ?? [];
  const overview = overviewState.kind === "ok" ? overviewState.value : null;

  const regressionsDelta = overview?.active_regressions_delta_30d ?? null;
  const improvementsDelta = overview?.improvements_delta_30d ?? null;
  const stats: Stat[] = [
    {
      label: <span className="inline-flex items-center gap-1.5"><AlertTriangle className="size-3 text-fail" /> Active regressions</span>,
      value: overview?.active_regressions ?? 0,
      unit: "P0",
      delta: regressionsDelta == null ? undefined : `${deltaArrow(regressionsDelta)} ${regressionsDelta} vs prev 30d`,
      deltaValue: regressionsDelta,
    },
    {
      label: <span className="inline-flex items-center gap-1.5"><TrendingUp className="size-3 text-pass" /> Improvements</span>,
      value: overview?.improvements ?? 0,
      unit: "tracked",
      delta: improvementsDelta == null ? undefined : `${deltaArrow(improvementsDelta)} ${improvementsDelta}`,
      deltaValue: improvementsDelta,
    },
    { label: <span className="inline-flex items-center gap-1.5"><Check className="size-3 text-pass" /> CI gate</span>, value: overview?.ci_gate.status ?? "passing", unit: "last 48h", delta: `${overview?.ci_gate.blocked_merges ?? 0} blocked merges`, deltaValue: 0 },
    { label: <span className="inline-flex items-center gap-1.5"><Bell className="size-3" /> Alerts (30d)</span>, value: overview?.alerts_fired_30d ?? 0, unit: "fired", delta: undefined, deltaValue: null },
    { label: <span className="inline-flex items-center gap-1.5"><Clock className="size-3" /> Last full sweep</span>, value: overview?.last_full_sweep_at ?? "", delta: undefined, deltaValue: null },
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
          { id: "overview", label: "Overview", active: activeTab === "overview", onSelect: () => setActiveTab("overview") },
          { id: "by_suite", label: "By suite", active: activeTab === "by_suite", onSelect: () => setActiveTab("by_suite") },
          { id: "by_model", label: "By model", active: activeTab === "by_model", onSelect: () => setActiveTab("by_model") },
          { id: "alerts", label: "Alerts", count: alertCount, active: activeTab === "alerts", onSelect: () => setActiveTab("alerts") },
          { id: "ci_gate", label: "CI gate", active: activeTab === "ci_gate", onSelect: () => setActiveTab("ci_gate") },
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
              <Button onClick={() => setActiveTab("alerts")}>
                <Bell className="size-3" /> Alert rules
                {alertCount != null && (
                  <span className="ml-1 font-mono text-[10.5px] bg-panel-3 text-muted-foreground px-1 py-px rounded">{alertCount}</span>
                )}
              </Button>
            </>
          }
        />

        {activeTab === "overview" && (
        <>
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
                      {showOperators && <span className="opacity-80 text-[10px] ml-0.5">· {operatorLegend.length}</span>}
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
            <AlertRulesPanel onNewRule={() => setActiveTab("alerts")} />
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
        </>
        )}

        {activeTab === "by_suite" && <BySuitePanel range={range === "custom" ? "30d" : range} />}
        {activeTab === "by_model" && <ByModelPanel range={range === "custom" ? "30d" : range} />}
        {activeTab === "alerts" && <AlertsTabPanel />}
        {activeTab === "ci_gate" && <CiGateTabPanel />}
      </div>
    </>
  );
}

function seriesSummary(values: (number | null)[]): { last: number; delta: number } {
  // Skip null buckets (days with no runs). Δ compares first vs last
  // populated day, not raw array ends.
  const present = values.filter((v): v is number => v != null);
  if (!present.length) return { last: 0, delta: 0 };
  const last = present[present.length - 1]!;
  const first = present[0]!;
  return { last, delta: last - first };
}

function BySuitePanel({ range }: { range: "7d" | "30d" | "90d" }): JSX.Element {
  const query = useTrendsSeries(range, false);
  const state = toState(query);
  return (
    <div className="p-5">
      <Panel>
        <PanelHeader title={<>By suite <span className="text-muted-foreground font-normal">· {range}</span></>} />
        <div className="p-3.5">
          {state.kind === "loading" && <LoadingSkeleton rows={4} columns={1} />}
          {state.kind === "error" && (
            <ErrorBanner message={state.message} retry={() => query.refetch()} />
          )}
          {state.kind === "empty" && <EmptyState title="No suite series yet." />}
          {state.kind === "ok" && (
            <table className="w-full text-[12px]">
              <thead className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
                <tr><th className="text-left py-1.5">Suite</th><th className="text-right">Last</th><th className="text-right">Δ {range}</th></tr>
              </thead>
              <tbody>
                {Object.entries(state.value.per_model).map(([suite, values]) => {
                  const { last, delta } = seriesSummary(values);
                  return (
                    <tr key={suite} className="border-t border-border">
                      <td className="py-1.5 font-mono">{suite}</td>
                      <td className="text-right tnum">{last.toFixed(1)}</td>
                      <td className={`text-right tnum ${delta >= 0 ? "text-pass" : "text-fail"}`}>{delta >= 0 ? "+" : ""}{delta.toFixed(1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Panel>
    </div>
  );
}

function ByModelPanel({ range }: { range: "7d" | "30d" | "90d" }): JSX.Element {
  const query = useTrendsSeries(range, false);
  const state = toState(query);
  return (
    <div className="p-5">
      <Panel>
        <PanelHeader title={<>By model <span className="text-muted-foreground font-normal">· {range}</span></>} />
        <div className="p-3.5">
          {state.kind === "loading" && <LoadingSkeleton rows={4} columns={1} />}
          {state.kind === "error" && (
            <ErrorBanner message={state.message} retry={() => query.refetch()} />
          )}
          {state.kind === "empty" && <EmptyState title="No model series yet." />}
          {state.kind === "ok" && (
            <table className="w-full text-[12px]">
              <thead className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
                <tr><th className="text-left py-1.5">Model</th><th className="text-right">Last</th><th className="text-right">Δ {range}</th></tr>
              </thead>
              <tbody>
                {Object.entries(state.value.per_model).map(([model, values]) => {
                  const { last, delta } = seriesSummary(values);
                  return (
                    <tr key={model} className="border-t border-border">
                      <td className="py-1.5 font-mono">{model}</td>
                      <td className="text-right tnum">{last.toFixed(1)}</td>
                      <td className={`text-right tnum ${delta >= 0 ? "text-pass" : "text-fail"}`}>{delta >= 0 ? "+" : ""}{delta.toFixed(1)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Panel>
    </div>
  );
}

function AlertsTabPanel(): JSX.Element {
  const query = useAlertRules();
  const state = toState(query);
  const createAlert = useCreateAlert();
  const deleteAlert = useDeleteAlert();
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [threshold, setThreshold] = useState("5");

  const submit = (): void => {
    if (!name.trim()) return;
    createAlert.mutate(
      { name: name.trim(), threshold_pct: Number(threshold) || 5 },
      {
        onSuccess: () => {
          setName("");
          setThreshold("5");
          setShowForm(false);
        },
      },
    );
  };

  return (
    <div className="p-5">
      <Panel>
        <PanelHeader
          title="Alert rules"
          actions={
            <Button size="sm" onClick={() => setShowForm((v) => !v)}>
              <Plus className="size-3" /> {showForm ? "Cancel" : "Create alert"}
            </Button>
          }
        />
        <div className="p-3.5 flex flex-col gap-3">
          {showForm && (
            <div className="flex items-end gap-2 p-3 border border-border rounded-md bg-panel-2">
              <label className="flex flex-col gap-1 text-[11px]">
                <span className="text-muted-foreground">Name</span>
                <input
                  className="h-7 px-2 rounded border border-border bg-background text-[12px]"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-[11px]">
                <span className="text-muted-foreground">Threshold %</span>
                <input
                  type="number"
                  step="0.1"
                  className="h-7 px-2 rounded border border-border bg-background text-[12px] w-24"
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                />
              </label>
              <Button size="sm" onClick={submit} disabled={createAlert.isPending || !name.trim()}>
                {createAlert.isPending ? "Saving…" : "Save"}
              </Button>
            </div>
          )}

          {state.kind === "loading" && <LoadingSkeleton rows={3} columns={1} />}
          {state.kind === "error" && (
            <ErrorBanner message={state.message} retry={() => query.refetch()} />
          )}
          {state.kind === "empty" && <EmptyState title="No alert rules configured." />}
          {state.kind === "ok" && (
            <table className="w-full text-[12px]">
              <thead className="text-[10.5px] uppercase tracking-wider text-muted-foreground">
                <tr>
                  <th className="text-left py-1.5">Name</th>
                  <th className="text-left">Condition</th>
                  <th className="text-left">Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {state.value.map((rule) => {
                  const r = rule as unknown as { id?: string; name: string; condition?: string; status?: string };
                  return (
                    <tr key={r.id ?? r.name} className="border-t border-border">
                      <td className="py-1.5 font-semibold">{r.name}</td>
                      <td className="font-mono text-[11px] text-foreground-2">{r.condition ?? "—"}</td>
                      <td className="text-muted-foreground">{r.status ?? "idle"}</td>
                      <td className="text-right">
                        {r.id && (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => deleteAlert.mutate(r.id!)}
                            disabled={deleteAlert.isPending}
                          >
                            <Trash2 className="size-3" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </Panel>
    </div>
  );
}

function CiGateTabPanel(): JSX.Element {
  const query = useTrendsCiGate();
  const state = toState(query);
  return (
    <div className="p-5">
      <Panel>
        <PanelHeader title="CI gate" />
        <div className="p-3.5">
          {state.kind === "loading" && <LoadingSkeleton rows={2} columns={1} />}
          {state.kind === "error" && (
            <ErrorBanner message={state.message} retry={() => query.refetch()} />
          )}
          {state.kind === "empty" && <EmptyState title="CI gate has no data yet." />}
          {state.kind === "ok" && (
            <dl className="grid grid-cols-2 gap-3 text-[12px]">
              <div><dt className="text-muted-foreground text-[10.5px] uppercase tracking-wider">Status</dt><dd className="font-semibold">{state.value.status}</dd></div>
              <div><dt className="text-muted-foreground text-[10.5px] uppercase tracking-wider">Blocked merges (48h)</dt><dd className="tnum">{state.value.blocked_merges_48h}</dd></div>
              <div><dt className="text-muted-foreground text-[10.5px] uppercase tracking-wider">Threshold</dt><dd className="tnum">{(state.value.threshold_pct * 100).toFixed(1)}%</dd></div>
              <div><dt className="text-muted-foreground text-[10.5px] uppercase tracking-wider">Computed at</dt><dd className="font-mono text-[11px]">{state.value.computed_at}</dd></div>
            </dl>
          )}
        </div>
      </Panel>
    </div>
  );
}
