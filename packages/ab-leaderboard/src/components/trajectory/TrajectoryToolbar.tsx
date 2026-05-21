import { ExternalLink, Share2, SplitSquareHorizontal } from "lucide-react";
import { Button } from "../ui/Button";
import { StatusPill } from "../ui/StatusPill";
import { ModelCell } from "../domain/ModelCell";
import { useDefaultTrajectory } from "../../api/hooks";

interface TrajectoryToolbarProps {
  compareOn: boolean;
  onToggleCompare: () => void;
}

export function TrajectoryToolbar({ compareOn, onToggleCompare }: TrajectoryToolbarProps): JSX.Element {
  const { data: trajectory } = useDefaultTrajectory();
  if (!trajectory) return <></>;
  return (
    <div className="flex items-center gap-3.5 px-6 py-2.5 border-b border-border bg-panel">
      <div className="flex items-center gap-2.5">
        <span className="font-mono text-muted-foreground text-[11.5px]">{trajectory.task.id}</span>
        <span className="font-semibold">{trajectory.task.title}</span>
        <StatusPill kind={trajectory.status} />
      </div>
      <div className="flex-1" />
      <div className="flex items-center gap-3 text-[11.5px]">
        <ModelCell model={trajectory.model} compact />
        <span className="text-muted-foreground/40">·</span>
        <span className="text-muted-foreground">run</span>
        <span className="font-mono">{trajectory.run_id}</span>
        <span className="text-muted-foreground/40">·</span>
        <span className="text-muted-foreground">{trajectory.duration_s}s</span>
        <span className="text-muted-foreground/40">·</span>
        <span className="font-mono text-accent">${trajectory.cost_usd.toFixed(4)}</span>
      </div>
      <div className="w-px h-6 bg-border" />
      <Button size="sm" variant={compareOn ? "primary" : "default"} onClick={onToggleCompare}>
        <SplitSquareHorizontal className="size-3" /> Compare with…
      </Button>
      <Button size="sm"><Share2 className="size-3" /> Share</Button>
      <Button size="sm" variant="ghost"><ExternalLink className="size-3" /></Button>
    </div>
  );
}
