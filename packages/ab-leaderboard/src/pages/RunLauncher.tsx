import { useState } from "react";
import { History, Play, RotateCcw, Terminal } from "lucide-react";
import { SubNav } from "../components/shell/SubNav";
import { PageHero } from "../components/shell/PageHero";
import { Button } from "../components/ui/Button";
import { TaskTree } from "../components/launcher/TaskTree";
import { RunConfigurator } from "../components/launcher/RunConfigurator";
import { ReplayMode } from "../components/launcher/ReplayMode";
import { LiveRunBanner } from "../components/launcher/LiveRunBanner";
import { taskById } from "../lib/mock-data";
import type { Task } from "../lib/types";

type Mode = "new" | "replay";

export default function RunLauncher(): JSX.Element {
  const [task, setTask] = useState<Task | null>(taskById("L1_001") ?? null);
  const [mode, setMode] = useState<Mode>("new");

  return (
    <>
      <SubNav
        crumbs={[{ label: "Runs" }, { label: "New run", current: true }]}
        tabs={[
          { id: "launcher", label: "Launcher", active: true },
          { id: "running", label: "In progress", count: 1 },
          { id: "recent", label: "Recent", count: 8 },
          { id: "scheduled", label: "Scheduled", count: 3 },
        ]}
        trailing={
          <Button size="sm">
            <Terminal className="size-3" /> ab run --suite L1
          </Button>
        }
      />
      <LiveRunBanner />

      <div className="flex flex-1 min-h-0">
        <div className="w-[340px] shrink-0 border-r border-border bg-background-2 overflow-hidden flex">
          <TaskTree selected={task} onSelect={setTask} />
        </div>

        <div className="flex-1 min-w-0 p-6 overflow-y-auto flex flex-col">
          <PageHero
            className="px-0 pt-0 pb-3.5 mb-5"
            title="Run launcher"
            subtitle="Configure once, launch across models. Cost estimate updates live."
            actions={
              <>
                <div className="flex border border-border rounded-md overflow-hidden">
                  <Button
                    size="sm"
                    variant={mode === "new" ? "primary" : "ghost"}
                    className="rounded-none border-0"
                    onClick={() => setMode("new")}
                  >
                    <Play className="size-3" fill="currentColor" /> New run
                  </Button>
                  <Button
                    size="sm"
                    variant={mode === "replay" ? "primary" : "ghost"}
                    className="rounded-none border-0"
                    onClick={() => setMode("replay")}
                  >
                    <RotateCcw className="size-3" /> Replay from commit
                  </Button>
                </div>
                <Button><History className="size-3" /> History</Button>
              </>
            }
          />

          {mode === "new" ? <RunConfigurator task={task} /> : <ReplayMode />}
        </div>
      </div>
    </>
  );
}
