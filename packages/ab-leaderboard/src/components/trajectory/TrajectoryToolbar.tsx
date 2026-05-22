import { Share2, SplitSquareHorizontal } from "lucide-react";
import { Button } from "../ui/Button";
import { StatusPill } from "../ui/StatusPill";
import type { RunStatus } from "../../lib/types";
import type { TrajectoryViewHeader } from "../../lib/types";

interface TrajectoryToolbarProps {
  header: TrajectoryViewHeader;
  compareOn: boolean;
  onToggleCompare: () => void;
}

const RUN_STATUSES: readonly RunStatus[] = [
  "completed",
  "timeout",
  "unrunnable",
  "error",
  "running",
];

function asRunStatus(status: string | null): RunStatus | null {
  return status && (RUN_STATUSES as readonly string[]).includes(status)
    ? (status as RunStatus)
    : null;
}

export function TrajectoryToolbar({ header, compareOn, onToggleCompare }: TrajectoryToolbarProps): JSX.Element {
  const status = asRunStatus(header.status);
  const cost = header.totals?.cost_usd;
  const latencyMs = header.totals?.latency_ms;
  return (
    <div className="flex items-center gap-3.5 px-6 py-2.5 border-b border-border bg-panel">
      <div className="flex items-center gap-2.5">
        {header.task_id && (
          <span className="font-mono text-muted-foreground text-[11.5px]">{header.task_id}</span>
        )}
        {status && <StatusPill kind={status} />}
      </div>
      <div className="flex-1" />
      <div className="flex items-center gap-3 text-[11.5px]">
        {header.model && <span className="font-mono">{header.model}</span>}
        {header.run_id && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span className="text-muted-foreground">run</span>
            <span className="font-mono">{header.run_id}</span>
          </>
        )}
        {latencyMs != null && latencyMs > 0 && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span className="text-muted-foreground">{(latencyMs / 1000).toFixed(1)}s</span>
          </>
        )}
        {cost != null && (
          <>
            <span className="text-muted-foreground/40">·</span>
            <span className="font-mono text-accent">${cost.toFixed(4)}</span>
          </>
        )}
      </div>
      <div className="w-px h-6 bg-border" />
      <Button size="sm" variant={compareOn ? "primary" : "default"} onClick={onToggleCompare}>
        <SplitSquareHorizontal className="size-3" /> Compare with…
      </Button>
      <Button size="sm" onClick={() => void navigator.clipboard?.writeText(window.location.href)}>
        <Share2 className="size-3" /> Share
      </Button>
    </div>
  );
}
