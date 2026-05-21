import { X } from "lucide-react";
import { Button } from "../ui/Button";

/** Persistent banner shown while a run is in progress. */
export function LiveRunBanner(): JSX.Element {
  return (
    <div className="flex items-center gap-3.5 px-6 py-2 bg-accent/[0.12] border-b border-accent/20 text-[12px]">
      <span className="relative size-2">
        <span className="absolute inset-0 rounded-full bg-accent" />
        <span className="absolute -inset-1 rounded-full bg-accent/25 animate-pulse-ring" />
      </span>
      <span className="font-mono text-foreground">ab-2026-21-05</span>
      <span className="text-muted-foreground">Smoke (CI) · 3 models · tier T0</span>
      <div className="flex-1 max-w-[280px]">
        <div className="h-1 w-full bg-panel-3 rounded-sm overflow-hidden">
          <div className="h-full bg-accent rounded-sm" style={{ width: "41%" }} />
        </div>
      </div>
      <span className="text-muted-foreground tnum">32 / 80 · 41%</span>
      <Button size="sm">Stream →</Button>
      <Button size="icon-sm" variant="ghost"><X className="size-3" /></Button>
    </div>
  );
}
