import { Info, Minus, Play, Plus } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { Panel, PanelHeader, PanelBody } from "../ui/Panel";
import { Button } from "../ui/Button";
import { Callout } from "../ui/Callout";
import { CheckBox } from "../ui/CheckBox";
import { TaskDetail } from "./TaskDetail";
import { MODELS, SUITES } from "../../lib/mock-data";
import type { Task, Vendor } from "../../lib/types";
import { cn } from "../../lib/utils";

const VENDOR_DOT_CLASS: Record<Vendor, string> = {
  anthropic: "bg-vendor-anthropic",
  openai: "bg-vendor-openai",
  google: "bg-vendor-google",
  zhipu: "bg-vendor-zhipu",
  minimax: "bg-vendor-minimax",
};

interface RunConfiguratorProps {
  task: Task | null;
}

const PRESETS = ["Smoke", "Full", "Memory only", "Custom"] as const;
type Preset = (typeof PRESETS)[number];

export function RunConfigurator({ task }: RunConfiguratorProps): JSX.Element {
  const [selectedModels, setSelectedModels] = useState<string[]>(["claude-sonnet-4-5", "gpt-5", "gemini-2.5-pro"]);
  const [selectedSuites, setSelectedSuites] = useState<string[]>(["L0_smoke", "L1_memory_write", "L1_retrieval"]);
  const [runs, setRuns] = useState(3);
  const [sandbox, setSandbox] = useState("Docker");
  const [preset, setPreset] = useState<Preset>("Custom");

  const totalTasks = useMemo(
    () =>
      SUITES.filter((s) => selectedSuites.includes(s.id)).reduce((n, s) => n + s.task_count, 0),
    [selectedSuites],
  );
  const trajectories = totalTasks * selectedModels.length * runs;
  const estCost = (trajectories * 0.04).toFixed(2);
  const estMin = Math.round(trajectories * 0.13);

  function toggleSuite(id: string): void {
    setSelectedSuites((arr) => (arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]));
  }
  function toggleModel(id: string): void {
    setSelectedModels((arr) => (arr.includes(id) ? arr.filter((x) => x !== id) : [...arr, id]));
  }

  return (
    <div className="flex flex-col gap-3.5">
      <TaskDetail task={task} />

      <Panel>
        <PanelHeader
          title="Run configurator"
          actions={
            <div className="flex gap-1">
              {PRESETS.map((p) => (
                <Button
                  key={p}
                  size="sm"
                  variant={preset === p ? "primary" : "ghost"}
                  onClick={() => setPreset(p)}
                >
                  {p}
                </Button>
              ))}
            </div>
          }
        />
        <PanelBody className="flex flex-col gap-5">
          <Field
            label="Suites"
            hint={`${selectedSuites.length} selected · ${totalTasks} tasks`}
            action={<Button size="sm" variant="ghost">Select all</Button>}
          >
            <div className="flex flex-wrap gap-1.5">
              {SUITES.map((s) => {
                const on = selectedSuites.includes(s.id);
                return (
                  <button
                    type="button"
                    key={s.id}
                    onClick={() => toggleSuite(s.id)}
                    className={cn(
                      "h-6 px-2.5 inline-flex items-center gap-1.5 rounded-full border text-[11.5px]",
                      on
                        ? "bg-accent/[0.12] border-accent/30 text-accent"
                        : "bg-panel-2 border-border text-foreground-2",
                    )}
                  >
                    <span className="font-mono text-muted-foreground">{s.layer}</span>
                    <span>{s.name}</span>
                    <span className="text-muted-foreground">·</span>
                    <span className="text-muted-foreground tnum">{s.task_count}</span>
                  </button>
                );
              })}
            </div>
          </Field>

          <Field
            label="Models"
            hint={`${selectedModels.length} selected`}
            action={<Button size="sm" variant="ghost">Select all</Button>}
          >
            <div className="grid gap-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
              {MODELS.map((m) => {
                const on = selectedModels.includes(m.id);
                return (
                  <button
                    type="button"
                    key={m.id}
                    onClick={() => toggleModel(m.id)}
                    className={cn(
                      "p-2.5 rounded-md border flex items-center gap-2.5 text-left",
                      on
                        ? "bg-accent/[0.12] border-accent shadow-[0_0_0_3px_hsl(var(--accent)/0.12)]"
                        : "bg-panel-2 border-border",
                    )}
                  >
                    <CheckBox checked={on} />
                    <div className="flex-1 min-w-0">
                      <div className="font-mono text-[11.5px] font-medium">{m.id}</div>
                      <div className="text-[10.5px] text-muted-foreground mt-0.5">
                        {m.harness} · ${m.cost_per_1k_in}/${m.cost_per_1k_out} per 1k
                      </div>
                    </div>
                    <span className={cn("size-2 rounded-full shrink-0", VENDOR_DOT_CLASS[m.vendor])} />
                  </button>
                );
              })}
            </div>
          </Field>

          <div className="grid grid-cols-3 gap-3.5">
            <Field label="Repetitions">
              <div className="flex items-center gap-1.5">
                <Button size="icon-sm" onClick={() => setRuns((r) => Math.max(1, r - 1))}><Minus className="size-3" /></Button>
                <input
                  className="flex-1 h-7 px-2 text-center rounded-md border border-border bg-panel-2 font-mono tnum text-[12px]"
                  value={runs}
                  onChange={(e) => setRuns(Math.max(1, +e.target.value || 1))}
                />
                <Button size="icon-sm" onClick={() => setRuns((r) => r + 1)}><Plus className="size-3" /></Button>
              </div>
              <div className="text-[10.5px] text-muted-foreground mt-1">For variance estimation</div>
            </Field>
            <Field label="Sandbox">
              <div className="flex gap-1">
                {(["Docker", "K8s", "Local"] as const).map((s) => (
                  <Button
                    key={s}
                    size="sm"
                    variant={sandbox === s ? "primary" : "default"}
                    className="flex-1 justify-center"
                    onClick={() => setSandbox(s)}
                  >
                    {s}
                  </Button>
                ))}
              </div>
              <div className="text-[10.5px] text-muted-foreground mt-1">Per-task isolation</div>
            </Field>
            <Field label="Concurrency">
              <input
                className="h-7 px-2.5 w-full rounded-md border border-border bg-panel-2 font-mono text-[12px]"
                defaultValue="4 parallel"
              />
              <div className="text-[10.5px] text-muted-foreground mt-1">Per-model lanes</div>
            </Field>
          </div>

          <Callout tone="accent" icon={<Info className="size-3.5" />}>
            <div className="flex items-center justify-between">
              <div>
                <strong>Cost estimate: ~${estCost}</strong>
                <span className="text-muted-foreground"> · {estMin} min · {trajectories} trajectories</span>
              </div>
              <span className="text-muted-foreground text-[11px]">Based on last 30d median cost/task</span>
            </div>
          </Callout>

          <div className="flex items-center justify-between border-t border-border-soft pt-3.5 -mt-1">
            <div className="text-muted-foreground text-[11px]">
              Results → <span className="font-mono text-foreground-2">./results/&lt;utc&gt;-&lt;run-id&gt;/</span>
            </div>
            <div className="flex items-center gap-2">
              <Button>Save preset</Button>
              <Button variant="primary" size="lg">
                <Play className="size-3.5" fill="currentColor" /> Launch run
              </Button>
            </div>
          </div>
        </PanelBody>
      </Panel>
    </div>
  );
}

function Field({
  label,
  hint,
  action,
  children,
}: {
  label: string;
  hint?: string;
  action?: ReactNode;
  children: ReactNode;
}): JSX.Element {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <div className="text-[11.5px] font-medium">
          {label}
          {hint && <span className="text-muted-foreground"> · {hint}</span>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}
