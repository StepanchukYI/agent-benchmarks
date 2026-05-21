import { Brain, CheckCircle2, Box, FileText, Pencil, Scale, User } from "lucide-react";
import { cn } from "../../lib/utils";
import type { TurnEvent } from "../../lib/types";

interface TurnTimelineProps {
  turns: TurnEvent[];
  active: number;
  onSelect: (idx: number) => void;
}

const ICON: Record<TurnEvent["icon"], (props: { className?: string }) => JSX.Element> = {
  cube: (p) => <Box {...p} />,
  "file-text": (p) => <FileText {...p} />,
  pencil: (p) => <Pencil {...p} />,
  brain: (p) => <Brain {...p} />,
  scale: (p) => <Scale {...p} />,
  "check-circle-2": (p) => <CheckCircle2 {...p} />,
  user: (p) => <User {...p} />,
};

const KIND_CHIP: Record<TurnEvent["kind"], string> = {
  prompt:  "bg-panel-3 text-foreground-2",
  tool:    "bg-info/[0.12] text-info",
  read:    "bg-panel-3 text-foreground-2",
  write:   "bg-accent/[0.12] text-accent",
  thought: "bg-panel-3 text-foreground-2",
  judge:   "bg-warn/[0.13] text-warn",
  verdict: "bg-pass/[0.12] text-pass",
};

export function TurnTimeline({ turns, active, onSelect }: TurnTimelineProps): JSX.Element {
  return (
    <ul className="flex flex-col">
      {turns.map((t) => {
        const Icon = ICON[t.icon];
        return (
          <li key={t.idx}>
            <button
              type="button"
              onClick={() => onSelect(t.idx)}
              className={cn(
                "w-full text-left flex items-start gap-2.5 px-3.5 py-2 border-l-2",
                active === t.idx
                  ? "bg-accent/[0.12] border-accent"
                  : "border-transparent hover:bg-panel-2",
              )}
            >
              <span className="w-[22px] text-right text-muted-foreground font-mono text-[10.5px] pt-0.5">
                {String(t.idx).padStart(2, "0")}
              </span>
              <span className={cn("size-[22px] grid place-items-center rounded-md shrink-0", KIND_CHIP[t.kind])}>
                <Icon className="size-3" />
              </span>
              <span className="flex-1 min-w-0">
                <span className="block text-[12px] font-medium">{t.label}</span>
                <span className="block text-[11px] text-muted-foreground mt-0.5 flex gap-2">
                  <span>{t.kind}</span>
                  <span className="font-mono">{t.meta}</span>
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
