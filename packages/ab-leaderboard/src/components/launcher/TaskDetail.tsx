import { Edit, Folder, Lock, Play } from "lucide-react";
import { type ReactNode } from "react";
import { Panel, PanelHeader, PanelBody } from "../ui/Panel";
import { Pill } from "../ui/Pill";
import { Button } from "../ui/Button";
import { Sparkline } from "../ui/Sparkline";
import type { Task } from "../../lib/types";

interface TaskDetailProps {
  task: Task | null;
}

function formatCostUsd(usd: number | null | undefined): string {
  if (usd == null) return "—";
  return `$${usd.toFixed(3)}`;
}

function formatPassRate(rate: number | null | undefined): string {
  if (rate == null) return "—";
  // Server returns 0..1, render as 0..100%.
  const pct = rate > 1 ? rate : rate * 100;
  return `${pct.toFixed(1)}%`;
}

function formatTurns(t: number | null | undefined): string {
  if (t == null) return "—";
  return String(t);
}

export function TaskDetail({ task }: TaskDetailProps): JSX.Element {
  if (!task) {
    return (
      <div className="rounded-lg border border-border-soft bg-background-2 p-9 text-center text-muted-foreground">
        <p>Select a task to preview</p>
      </div>
    );
  }

  const stats = task.stats;
  const passRate = stats?.pass_rate_30d ?? null;
  const runsCount = stats?.runs_count_30d ?? 0;
  const hasRuns = runsCount > 0;

  return (
    <Panel className="shrink-0">
      <PanelHeader
        title={
          <span className="flex items-center gap-2">
            <span className="font-mono text-muted-foreground">{task.id}</span>
            <span>{task.title}</span>
            {task.visibility === "private" && (
              <Pill tone="warn" size="sm">
                <Lock className="size-2.5" />
                private · self-reported
              </Pill>
            )}
          </span>
        }
        actions={
          <>
            <Button size="sm">
              <Play className="size-3" fill="currentColor" /> Dry-run
            </Button>
            <Button size="sm" variant="ghost"><Edit className="size-3" /></Button>
          </>
        }
      />
      <PanelBody className="flex gap-5">
        <div className="flex-1 flex flex-col gap-3">
          <Section label="SCORER CHAIN">
            {task.scorer_chain && task.scorer_chain.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {task.scorer_chain.map((s) => (
                  <Pill key={s.name} tone="accent" size="sm">
                    {s.name}
                  </Pill>
                ))}
              </div>
            ) : (
              <div className="text-[12px] text-muted-foreground">—</div>
            )}
          </Section>
          <Section label="FIXTURE">
            {task.fixture_ref ? (
              <div className="font-mono text-[11.5px] inline-flex items-center gap-1.5">
                <Folder className="size-3" />
                {task.fixture_ref}
              </div>
            ) : (
              <div className="text-[12px] text-muted-foreground">No fixture</div>
            )}
          </Section>
          <Section label="ACCEPTANCE">
            {task.acceptance_criteria && task.acceptance_criteria.length > 0 ? (
              <ul className="text-[12px] text-foreground-2 leading-relaxed list-disc pl-4 space-y-0.5">
                {task.acceptance_criteria.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            ) : (
              <div className="text-[12px] text-muted-foreground">—</div>
            )}
          </Section>
        </div>

        <div className="w-[200px] flex flex-col gap-3 border-l border-border-soft pl-5">
          <div>
            <Label>PASS RATE (30d)</Label>
            <div className="flex items-baseline gap-1.5">
              <span className="text-[22px] font-semibold tnum">{formatPassRate(passRate)}</span>
              {hasRuns ? null : <span className="text-[10px] text-muted-foreground">no runs</span>}
            </div>
            {hasRuns && passRate != null ? (
              <Sparkline data={[passRate * 100]} width={180} height={26} color="hsl(var(--accent))" fill />
            ) : (
              <div className="h-[26px]" aria-hidden />
            )}
          </div>
          <div>
            <Label>MEDIAN COST</Label>
            <div className="font-mono tnum text-[13px]">{formatCostUsd(stats?.median_cost_usd)}</div>
          </div>
          <div>
            <Label>MEDIAN TURNS</Label>
            <div className="font-mono tnum text-[13px]">{formatTurns(stats?.median_turns)}</div>
          </div>
          <div>
            <Label>RUNS (30d)</Label>
            <div className="font-mono tnum text-[13px]">{runsCount}</div>
          </div>
        </div>
      </PanelBody>
    </Panel>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }): JSX.Element {
  return (
    <div>
      <Label>{label}</Label>
      {children}
    </div>
  );
}

function Label({ children }: { children: ReactNode }): JSX.Element {
  return <div className="text-[10.5px] text-muted-foreground mb-1 tracking-wider">{children}</div>;
}
