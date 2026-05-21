import { useState } from "react";
import { Plus } from "lucide-react";
import { SubNav } from "../components/shell/SubNav";
import { PageHero } from "../components/shell/PageHero";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { LoadingSkeleton } from "../components/ui/LoadingSkeleton";
import { TaskTree } from "../components/launcher/TaskTree";
import { TaskDetail } from "../components/launcher/TaskDetail";
import { useTaskDetail, useTasksList } from "../api/hooks";
import { toState } from "../lib/ui-state";
import type { Task } from "../lib/types";

export default function Tasks(): JSX.Element {
  const tasksQuery = useTasksList();
  const tasksState = toState(tasksQuery);
  const tasks = tasksState.kind === "ok" ? tasksState.value : [];
  const defaultTask = tasks.find((t) => t.id === "L1_001") ?? null;
  const [task, setTask] = useState<Task | null>(defaultTask);
  // `useTasksList` returns a light shape (id/title/suite/layer/runs_count_30d
  // — no scorer_chain / acceptance_criteria / fixture_ref). Pull the full
  // detail for the selected task so TaskDetail can render real fields
  // instead of "—" placeholders.
  const detailQuery = useTaskDetail(task?.id);
  const detailedTask = detailQuery.data ?? task;
  const pilotCount = tasks.filter((t) => t.layer === "L0").length;
  const privateCount = tasks.filter((t) => (t as { visibility?: string }).visibility === "private").length;
  const evolvedCount = tasks.filter((t) => t.layer === "L5").length;
  return (
    <>
      <SubNav
        crumbs={[{ label: "Tasks" }, { label: "Library", current: true }]}
        tabs={[
          { id: "all", label: "All", active: true, count: tasks.length },
          { id: "pilot", label: "L0", count: pilotCount },
          { id: "private", label: "Private", count: privateCount },
          { id: "evolved", label: "L5 evolved", count: evolvedCount },
        ]}
      />
      <div className="flex flex-1 min-h-0">
        <div className="w-[340px] shrink-0 border-r border-border bg-background-2 overflow-hidden flex">
          <TaskTree selected={task} onSelect={setTask} />
        </div>
        <div className="flex-1 min-w-0 p-6 overflow-y-auto flex flex-col gap-4">
          <PageHero
            className="px-0 pt-0 pb-3.5"
            title="Task library"
            subtitle="Every task is a YAML in packages/ab-datasets. Hit `ab task validate` to lint before commit."
            actions={
              <Button variant="primary"><Plus className="size-3" /> New task</Button>
            }
          />
          {tasksState.kind === "loading" && <LoadingSkeleton rows={4} columns={2} />}
          {tasksState.kind === "error" && (
            <ErrorBanner
              message={tasksState.message}
              retry={() => tasksQuery.refetch()}
            />
          )}
          {tasksState.kind === "empty" && (
            <EmptyState
              title="No tasks registered yet."
              hint={
                <>
                  Run <span className="font-mono text-foreground-2">make schema-export</span> then drop a YAML under {" "}
                  <span className="font-mono text-foreground-2">packages/ab-datasets/ab_datasets/L&lt;N&gt;_&lt;theme&gt;/</span>.
                </>
              }
            />
          )}
          {tasksState.kind === "ok" && <TaskDetail task={detailedTask} />}
        </div>
      </div>
    </>
  );
}
