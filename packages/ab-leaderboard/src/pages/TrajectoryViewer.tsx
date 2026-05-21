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
import { PillarRadar } from "../components/charts/PillarRadar";
import { CostLedger } from "../components/charts/CostLedger";
import { TRAJECTORY } from "../lib/mock-data";
import { useTheme } from "../lib/theme";

export default function TrajectoryViewer(): JSX.Element {
  const { trajectoryLayout, setTrajectoryLayout } = useTheme();
  const [active, setActive] = useState<number>(6);
  const [compareOn, setCompareOn] = useState(false);
  const turn = TRAJECTORY.turns.find((t) => t.idx === active) ?? TRAJECTORY.turns[0]!;

  return (
    <>
      <SubNav
        crumbs={[
          { label: "Runs" },
          { label: "ab-2026-21-04", mono: true },
          { label: "Trajectories" },
          { label: "L1_001 · claude-sonnet-4-5", mono: true, current: true },
        ]}
        tabs={[
          { id: "overview", label: "Overview" },
          { id: "tasks", label: "Tasks", count: 80 },
          { id: "trajectories", label: "Trajectories", count: 240, active: true },
          { id: "cost", label: "Cost & Latency" },
          { id: "diff", label: "Diff vs prev" },
          { id: "export", label: "Export" },
        ]}
        trailing={
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
              <Button size="icon-sm"><ChevronLeft className="size-3" /></Button>
              <span className="text-muted-foreground font-mono tnum text-[11px] self-center px-1">14 / 80</span>
              <Button size="icon-sm"><ChevronRight className="size-3" /></Button>
            </div>
          </div>
        }
      />

      <CommitBreadcrumb />
      <TrajectoryToolbar compareOn={compareOn} onToggleCompare={() => setCompareOn((v) => !v)} />

      {trajectoryLayout === "three-pane" ? (
        <div className="flex flex-1 min-h-0">
          <aside className="w-[320px] shrink-0 border-r border-border bg-background-2 flex flex-col">
            <div className="flex items-center gap-2 px-3.5 py-2 border-b border-border-soft">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Timeline
              </span>
              <span className="text-muted-foreground text-[11px]">· {TRAJECTORY.turns.length} turns</span>
              <span className="flex-1" />
              <Button size="icon-sm" variant="ghost"><SlidersHorizontal className="size-3" /></Button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <TurnTimeline turns={TRAJECTORY.turns} active={active} onSelect={setActive} />
            </div>
          </aside>

          <main className="flex-1 min-w-0 bg-background flex flex-col">
            <TurnDetail turn={turn} />
          </main>

          <aside className="w-[320px] shrink-0 border-l border-border bg-background-2 p-3.5 flex flex-col gap-3.5 overflow-y-auto">
            <Panel>
              <PanelHeader title="Verdict" actions={<StatusPill kind="pass" size="sm" />} />
              <div className="p-3"><ScorerVerdictPanel /></div>
            </Panel>

            <PrivacyScrubber />

            <Panel>
              <PanelHeader title="Pillars" actions={<span className="text-[11px] text-muted-foreground">0–100</span>} />
              <div className="p-3">
                <div className="flex justify-center"><PillarRadar scores={TRAJECTORY.pillar_scores} size={190} /></div>
                <div className="flex flex-col gap-1.5 mt-2.5">
                  {Object.entries(TRAJECTORY.pillar_scores).map(([k, v]) => (
                    <div key={k} className="grid items-center gap-2" style={{ gridTemplateColumns: "1fr 60px 32px" }}>
                      <span className="text-muted-foreground text-[11px]">{k}</span>
                      <MiniBar value={v} tone={v > 85 ? "pass" : v > 70 ? "neutral" : "warn"} width="100%" />
                      <span className="font-mono text-[11px] font-semibold tnum text-right">{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            </Panel>

            <Panel>
              <PanelHeader title="Cost ledger" actions={<span className="text-[11px] text-muted-foreground">per turn</span>} />
              <div className="p-3"><CostLedger /></div>
            </Panel>
          </aside>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-[1100px] mx-auto p-5 flex flex-col gap-3.5">
            <div className="grid grid-cols-3 gap-3.5">
              <Panel className="col-span-2">
                <PanelHeader title="Verdict" actions={<StatusPill kind="pass" size="sm" />} />
                <div className="p-4 grid items-center gap-6" style={{ gridTemplateColumns: "1fr 220px" }}>
                  <ScorerVerdictPanel />
                  <div className="flex flex-col items-center">
                    <PillarRadar scores={TRAJECTORY.pillar_scores} size={200} />
                    <div className="text-muted-foreground text-[10.5px] mt-1.5">Pillar scores · 0–100</div>
                  </div>
                </div>
              </Panel>
              <Panel>
                <PanelHeader title="Cost ledger" />
                <div className="p-3"><CostLedger /></div>
              </Panel>
            </div>

            {TRAJECTORY.turns.map((t) => (
              <Panel key={t.idx} className={t.idx === active ? "ring-1 ring-accent" : ""}>
                <PanelHeader
                  title={
                    <span className="flex items-center gap-1.5">
                      <span className="font-mono text-muted-foreground text-[11px]">#{String(t.idx).padStart(2, "0")}</span>
                      <span>{t.label}</span>
                      <span className="text-muted-foreground font-normal text-[11px]">· {t.meta}</span>
                    </span>
                  }
                  actions={
                    <Button size="sm" variant="ghost" onClick={() => setActive(t.idx)}>focus →</Button>
                  }
                />
                <div className="p-3"><TurnDetail turn={t} /></div>
              </Panel>
            ))}
          </div>
        </div>
      )}
    </>
  );
}
