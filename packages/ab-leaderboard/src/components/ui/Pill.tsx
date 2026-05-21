import { type HTMLAttributes, forwardRef } from "react";
import { cn } from "../../lib/utils";

/**
 * Pill — small inline label with a leading status dot.
 * Tone is purely visual; semantics live on `aria-label`.
 */

export type PillTone =
  | "neutral"
  | "accent"
  | "pass"
  | "fail"
  | "warn"
  | "info"
  | "idle";

export type PillSize = "sm" | "md" | "lg";

export interface PillProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: PillTone;
  size?: PillSize;
  /** Hide the leading dot. */
  noDot?: boolean;
}

const TONE_CLASS: Record<PillTone, string> = {
  neutral: "bg-panel-2 text-foreground-2 border border-border",
  accent:  "bg-accent/[0.12] text-accent",
  pass:    "bg-pass/[0.12] text-pass",
  fail:    "bg-fail/[0.12] text-fail",
  warn:    "bg-warn/[0.13] text-warn",
  info:    "bg-info/[0.12] text-info",
  idle:    "bg-idle/[0.16] text-muted-foreground",
};

const SIZE_CLASS: Record<PillSize, string> = {
  sm: "h-[18px] px-1.5 text-[10px]",
  md: "h-5 px-[7px] text-[11px]",
  lg: "h-6 px-2.5 text-[11.5px]",
};

export const Pill = forwardRef<HTMLSpanElement, PillProps>(function Pill(
  { tone = "neutral", size = "md", noDot = false, className, children, ...rest },
  ref,
) {
  return (
    <span
      ref={ref}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium tnum whitespace-nowrap",
        SIZE_CLASS[size],
        TONE_CLASS[tone],
        className,
      )}
      {...rest}
    >
      {!noDot && <span className="size-[5px] rounded-full bg-current" />}
      {children}
    </span>
  );
});
