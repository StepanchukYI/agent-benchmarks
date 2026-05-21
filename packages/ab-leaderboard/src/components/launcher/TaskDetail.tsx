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

export function TaskDetail({ task }: TaskDetailProps): JSX.Element {
  if (!task) {
    return (
      <div className="rounded-lg border border-border-soft bg-background-2 p-9 text-center text-muted-foreground">
        <p>Select a task to preview</p>
      </div>
    );
  }

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
            <div className="flex flex-wrap gap-1.5">
              {task.scorer_chain?.map((s) => (
                <Pill key={s.name} tone="accent" size="sm">
                  {s.name}
                </Pill>
              ))}
            </div>
          </Section>
          <Section label="FIXTURE">
            <div className="font-mono text-[11.5px] inline-flex items-center gap-1.5">
              <Folder className="size-3" />
              vault-medium-2026-05.tar.gz
              <span className="text-muted-foreground ml-2">· 4.8 MB · sha256:a7c2…b09f</span>
            </div>
          </Section>
          <Section label="ACCEPTANCE">
            <div className="text-[12px] text-foreground-2 leading-relaxed">
              File <span className="font-mono">decisions/&lt;slug&gt;.md</span> created with frontmatter{" "}
              <span className="font-mono">{`{status, decided_by, supersedes?}`}</span> validating against{" "}
              <span className="font-mono">schemas/decision.v2.json</span>; body includes{" "}
              <span className="font-mono">## Context</span>,{" "}
              <span className="font-mono">## Decision</span>,{" "}
              <span className="font-mono">## Consequences</span> sections; vault diff contains{" "}
              <strong>no</strong> deletions.
            </div>
          </Section>
        </div>

        <div className="w-[200px] flex flex-col gap-3 border-l border-border-soft pl-5">
          <div>
            <Label>PASS RATE (30d)</Label>
            <div className="flex items-baseline gap-1.5">
              <span className="text-[22px] font-semibold tnum">{task.pass_rate ?? "—"}%</span>
              <span className="text-[10px] tnum text-pass">▲ 4.2</span>
            </div>
            <Sparkline data={sampleSpark(task.pass_rate ?? 80)} width={180} height={26} color="hsl(var(--accent))" fill />
          </div>
          <div>
            <Label>MEDIAN COST</Label>
            <div className="font-mono tnum text-[13px]">$0.041</div>
          </div>
          <div>
            <Label>MEDIAN TURNS</Label>
            <div className="font-mono tnum text-[13px]">9</div>
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

function sampleSpark(base: number): number[] {
  const arr: number[] = [];
  let v = base;
  let s = 91;
  for (let i = 0; i < 12; i++) {
    s = (s * 9301 + 49297) % 233280;
    const r = s / 233280;
    v += (r - 0.5) * 2.4;
    arr.push(+v.toFixed(1));
  }
  return arr;
}
