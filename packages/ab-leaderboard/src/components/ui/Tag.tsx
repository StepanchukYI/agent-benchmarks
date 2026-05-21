import { type HTMLAttributes } from "react";
import { cn } from "../../lib/utils";

/** Compact monospace tag used for short metadata (scorer kinds, tier ids, …). */
export function Tag({ className, ...rest }: HTMLAttributes<HTMLSpanElement>): JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 h-[18px] px-1.5 rounded font-mono text-[10.5px] bg-panel-3 text-muted-foreground",
        className,
      )}
      {...rest}
    />
  );
}

/** Keyboard shortcut chip. */
export function Kbd({ className, ...rest }: HTMLAttributes<HTMLSpanElement>): JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex items-center px-1.5 py-[1px] rounded border border-border bg-panel-3 font-mono text-[10.5px] text-muted-foreground",
        className,
      )}
      {...rest}
    />
  );
}
