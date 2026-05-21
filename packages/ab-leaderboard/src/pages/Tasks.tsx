import { useState } from "react";
import { Plus } from "lucide-react";
import { SubNav } from "../components/shell/SubNav";
import { PageHero } from "../components/shell/PageHero";
import { Button } from "../components/ui/Button";
import { TaskTree } from "../components/launcher/TaskTree";
import { TaskDetail } from "../components/launcher/TaskDetail";
import { useTasksList } from "../api/hooks";
import type { Task } from "../lib/types";

export default function Tasks(): JSX.Element {
  const { data: tasks } = useTasksList();
  const defaultTask = (tasks ?? []).find((t) => t.id === "L1_001") ?? null;
  const [task, setTask] = useState<Task | null>(defaultTask);
  return (
    <>
      <SubNav
        crumbs={[{ label: "Tasks" }, { label: "Library", current: true }]}
        tabs={[
          { id: "all", label: "All", active: true, count: 159 },
          { id: "pilot", label: "Pilot", count: 12 },
          { id: "private", label: "Private", count: 5 },
          { id: "evolved", label: "L5 evolved", count: 0 },
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
          <TaskDetail task={task} />
        </div>
      </div>
    </>
  );
}
