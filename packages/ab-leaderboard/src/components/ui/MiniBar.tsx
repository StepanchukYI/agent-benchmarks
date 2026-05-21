import { cn } from "../../lib/utils";

interface MiniBarProps {
  value: number;
  max?: number;
  /** Color preset. */
  tone?: "neutral" | "pass" | "warn" | "fail";
  width?: number | string;
  className?: string;
}

export function MiniBar({
  value,
  max = 100,
  tone = "neutral",
  width = 56,
  className,
}: MiniBarProps): JSX.Element {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const toneClass: Record<NonNullable<MiniBarProps["tone"]>, string> = {
    neutral: "bg-accent",
    pass: "bg-pass",
    warn: "bg-warn",
    fail: "bg-fail",
  };
  return (
    <span
      className={cn("inline-block relative align-middle h-1 rounded-sm bg-panel-3 overflow-hidden", className)}
      style={{ width }}
      aria-valuenow={value}
      aria-valuemax={max}
      role="progressbar"
    >
      <span className={cn("block h-full rounded-sm", toneClass[tone])} style={{ width: `${pct}%` }} />
    </span>
  );
}
