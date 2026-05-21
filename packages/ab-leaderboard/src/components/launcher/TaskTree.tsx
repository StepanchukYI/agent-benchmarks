import { ChevronDown, ChevronRight, Folder, Lock, Plus, Search, SlidersHorizontal, Unlock } from "lucide-react";
import { useState } from "react";
import { Button } from "../ui/Button";
import { Tag } from "../ui/Tag";
import { useSuites, useTasksList } from "../../api/hooks";
import type { Layer, Suite, Task } from "../../lib/types";
import { cn } from "../../lib/utils";

interface TaskTreeProps {
  selected: Task | null;
  onSelect: (task: Task) => void;
}

const DIFFICULTY_COLOR: Record<NonNullable<Task["difficulty"]>, string> = {
  easy:   "bg-pass/[0.12] text-pass",
  medium: "bg-warn/[0.13] text-warn",
  hard:   "bg-fail/[0.12] text-fail",
};

const DIFFICULTY_LETTER: Record<NonNullable<Task["difficulty"]>, string> = {
  easy: "E",
  medium: "M",
  hard: "H",
};

export function TaskTree({ selected, onSelect }: TaskTreeProps): JSX.Element {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState<Record<Layer, boolean>>({
    L0: true, L1: true, L2: false, L3: false, L4: false, L5: false,
  });
  const { data: suites } = useSuites();
  const { data: tasks } = useTasksList();
  const suiteList: Suite[] = suites ?? [];
  const taskList: Task[] = tasks ?? [];

  const byLayer = suiteList.reduce<Record<string, Suite[]>>((acc, s) => {
    (acc[s.layer] ||= []).push(s);
    return acc;
  }, {});

  const tasksBySuite = taskList.reduce<Record<string, Task[]>>((acc, t) => {
    (acc[t.suite] ||= []).push(t);
    return acc;
  }, {});

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="px-3.5 pt-3 pb-2 flex flex-col gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tasks, IDs, tags…"
            className="h-7 w-full pl-7 pr-2 rounded-md border border-border bg-panel-2 text-[12px] placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex items-center gap-1 text-[11px]">
          <span className="text-muted-foreground">{taskList.length} tasks</span>
          <span className="flex-1" />
          <Button size="sm" variant="ghost"><SlidersHorizontal className="size-3" /> Filter</Button>
          <Button size="sm" variant="ghost"><Plus className="size-3" /> New</Button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto min-h-0 pb-5">
        {(Object.entries(byLayer) as [Layer, Suite[]][]).map(([layer, suites]) => (
          <div key={layer}>
            <button
              type="button"
              onClick={() => setOpen((o) => ({ ...o, [layer]: !o[layer] }))}
              className="w-full flex items-center gap-2 px-3.5 py-1.5 font-semibold text-foreground hover:bg-panel-2"
            >
              {open[layer] ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
              <span className="flex-1 text-left">{layer}</span>
              <span className="text-muted-foreground text-[11px]">
                {suites.reduce((n, s) => n + (tasksBySuite[s.id]?.length ?? 0), 0)}
              </span>
            </button>

            {open[layer] && suites.map((s) => (
              <div key={s.id}>
                <div className="flex items-center gap-2 px-3.5 py-1 pl-7 text-foreground-2">
                  <Folder className="size-3" />
                  <span className="flex-1 text-[12px]">{s.name}</span>
                  <span className="text-muted-foreground text-[11px]">
                    {(tasksBySuite[s.id]?.length ?? 0)}
                  </span>
                </div>

                {(tasksBySuite[s.id] ?? [])
                  .filter((t) => !search || t.title.toLowerCase().includes(search.toLowerCase()) || t.id.toLowerCase().includes(search.toLowerCase()))
                  .map((t) => {
                    const sel = selected?.id === t.id;
                    const isPrivate = t.visibility === "private";
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => onSelect(t)}
                        className={cn(
                          "w-full flex items-center gap-2 pl-12 pr-3.5 py-1 border-l-2 text-left",
                          sel
                            ? "bg-accent/[0.12] border-accent"
                            : "border-transparent hover:bg-panel-2",
                        )}
                      >
                        <span className="font-mono text-[10px] text-muted-foreground flex items-center gap-1 w-[60px]">
                          <span title={isPrivate ? "Private — requires personal vault snapshot. Self-reported only." : "Public task"}>
                            {isPrivate
                              ? <Lock className="size-3 text-warn" aria-hidden />
                              : <Unlock className="size-3 text-muted-foreground/60" aria-hidden />}
                          </span>
                          {t.id}
                        </span>
                        <span className="flex-1 text-[12px] truncate">{t.title}</span>
                        {t.difficulty && (
                          <Tag className={DIFFICULTY_COLOR[t.difficulty]}>
                            {DIFFICULTY_LETTER[t.difficulty]}
                          </Tag>
                        )}
                      </button>
                    );
                  })}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
