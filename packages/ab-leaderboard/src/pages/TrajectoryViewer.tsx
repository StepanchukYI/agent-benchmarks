import { useState } from "react";
import { ChevronLeft, ChevronRight, SlidersHorizontal } from "lucide-react";
import { SubNav } from "../components/shell/SubNav";
import { CommitBreadcrumb } from "../components/trajectory/CommitBreadcrumb";
import { TrajectoryToolbar } from "../components/trajectory/TrajectoryToolbar";
import { TurnTimeline } from "../components/trajectory/TurnTimeline";
import { TurnDetail } from "../components/trajectory/TurnDetail";
import { PrivacyScrubber } from "../components/trajectory/PrivacyScrubber";
import { ScorerVerdictPanel } from "../components/trajectory/ScorerVerdictPanel";
import { Panel, PanelHeader } from "../components/ui/Panel";
import { Button } from "../components/ui/Button";
import { StatusPill } from "../components/ui/StatusPill";
import { MiniBar } from "../components/ui/MiniBar";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { LoadingSkeleton } from "../components/ui/LoadingSkeleton";
import { PillarRadar } from "../components/charts/PillarRadar";
import { CostLedger } from "../components/charts/CostLedger";
import { useDefaultTrajectory, useSubmissionsList, useTasksList } from "../api/hooks";
import { toState } from "../lib/ui-state";
import { useTheme } from "../lib/theme";
import type { Task, TrajectoryView } from "../lib/types";

type TabId = "overview" | "tasks" | "trajectories" | "cost" | "diff" | "export";

export default function TrajectoryViewer(): JSX.Element {
  const { trajectoryLayout, setTrajectoryLayout } = useTheme();
  const [active, setActive] = useState<number>(0);
  const [activeTab, setActiveTab] = useState<TabId>("trajectories");
  const [compareOn, setCompareOn] = useState(false);
  const trajectoryQuery = useDefaultTrajectory();
  const tasksQuery = useTasksList();
  const submissionsQuery = useSubmissionsList();
  // null (404 / no public trajectory) and a turnless payload both → EmptyState.
  const trajectoryState = toState(
    trajectoryQuery,
    (t: TrajectoryView | null) => !t || t.turns.length === 0,
  );

  const tasksCount = tasksQuery.data?.length ?? 0;
  const submissionsCount = submissionsQuery.data?.length ?? 0;

  const view = trajectoryState.kind === "ok" ? trajectoryState.value : null;
  const turnCount = view?.turns.length ?? 0;
  const activePos = view ? view.turns.findIndex((t) => t.idx === active) : -1;
  const crumbModel = view?.header.model ?? null;
  const crumbTask = view?.header.task_id ?? null;
  const crumbRun = view?.header.run_id ?? null;

  const stepTurn = (dir: -1 | 1): void => {
    if (!view || view.turns.length === 0) return;
    const cur = activePos < 0 ? 0 : activePos;
    const next = Math.min(Math.max(cur + dir, 0), view.turns.length - 1);
    setActive(view.turns[next]!.idx);
  };

  return (
    <>
      <SubNav
        crumbs={[
          { label: "Runs" },
          ...(crumbRun ? [{ label: crumbRun, mono: true }] : []),
          { label: "Trajectories" },
          ...(crumbTask || crumbModel
            ? [{ label: [crumbTask, crumbModel].filter(Boolean).join(" · "), mono: true, current: true }]
            : []),
        ]}
        tabs={[
          { id: "overview", label: "Overview", active: activeTab === "overview", onSelect: () => setActiveTab("overview") },
          { id: "tasks", label: "Tasks", count: tasksCount, active: activeTab === "tasks", onSelect: () => setActiveTab("tasks") },
          { id: "trajectories", label: "Trajectories", count: submissionsCount, active: activeTab === "trajectories", onSelect: () => setActiveTab("trajectories") },
          { id: "cost", label: "Cost & Latency", active: activeTab === "cost", onSelect: () => setActiveTab("cost") },
          { id: "diff", label: "Diff vs prev", active: activeTab === "diff", onSelect: () => setActiveTab("diff") },
          { id: "export", label: "Export", active: activeTab === "export", onSelect: () => setActiveTab("export") },
        ]}
        trailing={
          activeTab === "trajectories" ? (
            <div className="flex items-center gap-1.5">
              <div className="flex border border-border rounded-md overflow-hidden">
                <Button
                  size="sm"
                  variant={trajectoryLayout === "three-pane" ? "primary" : "ghost"}
                  className="rounded-none border-0"
                  onClick={() => setTrajectoryLayout("three-pane")}
                >
                  3-pane
                </Button>
                <Button
                  size="sm"
                  variant={trajectoryLayout === "stacked" ? "primary" : "ghost"}
                  className="rounded-none border-0"
                  onClick={() => setTrajectoryLayout("stacked")}
                >
                  Stacked
                </Button>
              </div>
              <div className="flex gap-1 ml-2">
                <Button size="icon-sm" onClick={() => stepTurn(-1)} disabled={turnCount === 0 || activePos <= 0}>
                  <ChevronLeft className="size-3" />
                </Button>
                <span className="text-muted-foreground font-mono tnum text-[11px] self-center px-1">
                  {turnCount === 0 ? "—" : `${(activePos < 0 ? 0 : activePos) + 1} / ${turnCount}`}
                </span>
                <Button size="icon-sm" onClick={() => stepTurn(1)} disabled={turnCount === 0 || activePos >= turnCount - 1}>
                  <ChevronRight className="size-3" />
                </Button>
              </div>
            </div>
          ) : undefined
        }
      />

      {activeTab === "overview" && (
        <OverviewTab
          tasksCount={tasksCount}
          submissionsCount={submissionsCount}
          lastUpdated={submissionsQuery.data?.[0]?.ingested_at}
        />
      )}

      {activeTab === "tasks" && <TasksTab tasks={tasksQuery.data ?? []} />}

      {activeTab === "trajectories" && (
        <>
          {trajectoryState.kind === "loading" && (
            <div className="p-5"><LoadingSkeleton rows={6} columns={3} /></div>
          )}
          {trajectoryState.kind === "error" && (
            <div className="p-5">
              <ErrorBanner
                message={trajectoryState.message}
                retry={() => trajectoryQuery.refetch()}
              />
            </div>
          )}
          {trajectoryState.kind === "empty" && (
            <div className="p-5">
              <EmptyState
                title="No public trajectory yet."
                hint="A trajectory appears here once a public submission is ingested and re-scored."
              />
            </div>
          )}
          {trajectoryState.kind === "ok" && view && (
            <>
              <CommitBreadcrumb trust={view.trust} header={view.header} />
              <TrajectoryToolbar
                header={view.header}
                compareOn={compareOn}
                onToggleCompare={() => setCompareOn((v) => !v)}
              />
              <TrajectoryBody
                view={view}
                layout={trajectoryLayout}
                active={active}
                setActive={setActive}
              />
            </>
          )}
        </>
      )}

      {(activeTab === "cost" || activeTab === "diff" || activeTab === "export") && (
        <div className="p-5">
          <EmptyState
            title="Coming soon"
            hint="Cost/Diff/Export tabs require additional backend endpoints."
          />
        </div>
      )}
    </>
  );
}

interface OverviewTabProps {
  tasksCount: number;
  submissionsCount: number;
  lastUpdated: string | undefined;
}

function OverviewTab({ tasksCount, submissionsCount, lastUpdated }: OverviewTabProps): JSX.Element {
  return (
    <div className="p-5">
      <Panel>
        <PanelHeader title="Overview" />
        <div className="p-4 grid grid-cols-3 gap-4 text-[12px]">
          <div>
            <div className="text-muted-foreground text-[11px] uppercase tracking-wider">Tasks</div>
            <div className="font-mono tnum text-[18px] mt-1">{tasksCount}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-[11px] uppercase tracking-wider">Submissions</div>
            <div className="font-mono tnum text-[18px] mt-1">{submissionsCount}</div>
          </div>
          <div>
            <div className="text-muted-foreground text-[11px] uppercase tracking-wider">Last updated</div>
            <div className="font-mono tnum text-[12px] mt-2">{lastUpdated ?? "—"}</div>
          </div>
        </div>
      </Panel>
    </div>
  );
}

interface TasksTabProps {
  tasks: Task[];
}

function TasksTab({ tasks }: TasksTabProps): JSX.Element {
  if (tasks.length === 0) {
    return (
      <div className="p-5">
        <EmptyState
          title="No tasks loaded"
          hint="Tasks appear once the server returns a populated `/tasks` payload."
        />
      </div>
    );
  }
  return (
    <div className="flex-1 overflow-y-auto p-5">
      <Panel>
        <PanelHeader title={`Tasks · ${tasks.length}`} />
        <ul className="divide-y divide-border-soft">
          {tasks.map((t) => (
            <li key={t.id} className="px-4 py-2 flex items-center gap-3 text-[12px]">
              <span className="font-mono text-muted-foreground tnum w-[120px] shrink-0">{t.id}</span>
              <span className="flex-1 truncate">{t.title}</span>
              <span className="text-muted-foreground text-[11px]">{t.layer}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}

interface TrajectoryBodyProps {
  view: TrajectoryView;
  layout: "three-pane" | "stacked";
  active: number;
  setActive: (n: number) => void;
}

/**
 * Verdict pill kind from the real scorer chain: pass only if every decided
 * scorer passed. "info" stands in for "pending" — StatusPill's kind union has
 * no "pending", so an undecided/empty chain renders as a neutral info pill.
 */
function verdictKind(scorers: TrajectoryView["scorers"]): "pass" | "fail" | "info" {
  const decided = scorers.filter((s) => s.pass != null);
  if (decided.length === 0) return "info";
  return decided.every((s) => s.pass) ? "pass" : "fail";
}

/** Pillar map with nulls dropped — PillarRadar + the bar list only plot real scores. */
function realPillars(pillars: TrajectoryView["pillars"]): Record<string, number> {
  const out: Record<string, number> = {};
  if (!pillars) return out;
  for (const [k, v] of Object.entries(pillars)) {
    if (v != null) out[k] = v;
  }
  return out;
}

function TrajectoryBody({ view, layout, active, setActive }: TrajectoryBodyProps): JSX.Element {
  const turns = view.turns;
  const events = view.events;
  const activeEvent = events.find((e) => e.idx === active) ?? events[0]!;
  const turn = turns.find((t) => t.idx === active);
  const verdict = verdictKind(view.scorers);
  const pillars = realPillars(view.pillars);

  if (layout === "three-pane") {
    return (
      <div className="flex flex-1 min-h-0">
        <aside className="w-[320px] shrink-0 border-r border-border bg-background-2 flex flex-col">
          <div className="flex items-center gap-2 px-3.5 py-2 border-b border-border-soft">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Timeline
            </span>
            <span className="text-muted-foreground text-[11px]">· {events.length} turns</span>
            <span className="flex-1" />
            <Button size="icon-sm" variant="ghost"><SlidersHorizontal className="size-3" /></Button>
          </div>
          <div className="flex-1 overflow-y-auto">
            <TurnTimeline turns={events} active={active} onSelect={setActive} />
          </div>
        </aside>

        <main className="flex-1 min-w-0 bg-background flex flex-col">
          <TurnDetail event={activeEvent} turn={turn} />
        </main>

        <aside className="w-[320px] shrink-0 border-l border-border bg-background-2 p-3.5 flex flex-col gap-3.5 overflow-y-auto">
          <Panel>
            <PanelHeader title="Verdict" actions={<StatusPill kind={verdict} size="sm" />} />
            <div className="p-3"><ScorerVerdictPanel scorers={view.scorers} /></div>
          </Panel>

          <PrivacyScrubber submissionId={view.submission_id} />

          {Object.keys(pillars).length > 0 && (
            <Panel>
              <PanelHeader title="Pillars" actions={<span className="text-[11px] text-muted-foreground">0–100</span>} />
              <div className="p-3">
                <div className="flex justify-center"><PillarRadar scores={pillars} size={190} /></div>
                <div className="flex flex-col gap-1.5 mt-2.5">
                  {Object.entries(pillars).map(([k, v]) => (
                    <div key={k} className="grid items-center gap-2" style={{ gridTemplateColumns: "1fr 60px 32px" }}>
                      <span className="text-muted-foreground text-[11px]">{k}</span>
                      <MiniBar value={v} tone={v > 85 ? "pass" : v > 70 ? "neutral" : "warn"} width="100%" />
                      <span className="font-mono text-[11px] font-semibold tnum text-right">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            </Panel>
          )}

          <Panel>
            <PanelHeader title="Cost ledger" actions={<span className="text-[11px] text-muted-foreground">per turn</span>} />
            <div className="p-3"><CostLedger turns={turns} totals={view.header.totals} /></div>
          </Panel>
        </aside>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-[1100px] mx-auto p-5 flex flex-col gap-3.5">
        <div className="grid grid-cols-3 gap-3.5">
          <Panel className="col-span-2">
            <PanelHeader title="Verdict" actions={<StatusPill kind={verdict} size="sm" />} />
            <div className="p-4 grid items-center gap-6" style={{ gridTemplateColumns: "1fr 220px" }}>
              <ScorerVerdictPanel scorers={view.scorers} />
              {Object.keys(pillars).length > 0 && (
                <div className="flex flex-col items-center">
                  <PillarRadar scores={pillars} size={200} />
                  <div className="text-muted-foreground text-[10.5px] mt-1.5">Pillar scores · 0–100</div>
                </div>
              )}
            </div>
          </Panel>
          <Panel>
            <PanelHeader title="Cost ledger" />
            <div className="p-3"><CostLedger turns={turns} totals={view.header.totals} /></div>
          </Panel>
        </div>

        {events.map((e) => {
          const t = turns.find((tt) => tt.idx === e.idx);
          return (
            <Panel key={e.idx} className={e.idx === active ? "ring-1 ring-accent" : ""}>
              <PanelHeader
                title={
                  <span className="flex items-center gap-1.5">
                    <span className="font-mono text-muted-foreground text-[11px]">#{String(e.idx).padStart(2, "0")}</span>
                    <span>{e.label}</span>
                    {e.meta && <span className="text-muted-foreground font-normal text-[11px]">· {e.meta}</span>}
                  </span>
                }
                actions={
                  <Button size="sm" variant="ghost" onClick={() => setActive(e.idx)}>focus →</Button>
                }
              />
              <div className="p-3"><TurnDetail event={e} turn={t} /></div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
}
