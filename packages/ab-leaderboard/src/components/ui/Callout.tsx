import { type ReactNode } from "react";
import { Info, AlertTriangle, ShieldCheck } from "lucide-react";
import { cn } from "../../lib/utils";

export type CalloutTone = "info" | "accent" | "warn" | "success";

interface CalloutProps {
  tone?: CalloutTone;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}

const TONE: Record<CalloutTone, { wrap: string; icon: string }> = {
  info:    { wrap: "bg-panel-2 border-border text-foreground-2",         icon: "text-muted-foreground" },
  accent:  { wrap: "bg-accent/[0.12] border-accent/30 text-foreground",  icon: "text-accent" },
  warn:    { wrap: "bg-warn/[0.13] border-warn/30 text-foreground",      icon: "text-warn" },
  success: { wrap: "bg-pass/[0.12] border-pass/30 text-foreground",      icon: "text-pass" },
};

const DEFAULT_ICON: Record<CalloutTone, ReactNode> = {
  info:    <Info className="size-3.5" />,
  accent:  <Info className="size-3.5" />,
  warn:    <AlertTriangle className="size-3.5" />,
  success: <ShieldCheck className="size-3.5" />,
};

export function Callout({ tone = "info", icon, children, className }: CalloutProps): JSX.Element {
  const t = TONE[tone];
  return (
    <div className={cn("flex items-start gap-2.5 px-3 py-2.5 rounded-lg border text-[12px]", t.wrap, className)}>
      <span className={cn("shrink-0 mt-0.5", t.icon)}>{icon ?? DEFAULT_ICON[tone]}</span>
      <div className="flex-1">{children}</div>
    </div>
  );
}
