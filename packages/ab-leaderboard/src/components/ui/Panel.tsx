import { type HTMLAttributes, type ReactNode } from "react";
import { cn } from "../../lib/utils";

export interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  flat?: boolean;
}

export function Panel({ flat = false, className, ...rest }: PanelProps): JSX.Element {
  return (
    <div
      className={cn(
        "rounded-lg border border-border",
        flat ? "bg-background-2" : "bg-panel",
        className,
      )}
      {...rest}
    />
  );
}

export interface PanelHeaderProps {
  title: ReactNode;
  hint?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function PanelHeader({ title, hint, actions, className }: PanelHeaderProps): JSX.Element {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 px-3.5 py-2.5 border-b border-border",
        className,
      )}
    >
      <div className="flex items-center gap-2 text-[12px] font-semibold tracking-tight">
        {title}
        {hint != null && (
          <span className="font-normal text-muted-foreground text-[11px]">· {hint}</span>
        )}
      </div>
      {actions != null && <div className="flex items-center gap-1.5">{actions}</div>}
    </div>
  );
}

export function PanelBody({
  className,
  ...rest
}: HTMLAttributes<HTMLDivElement>): JSX.Element {
  return <div className={cn("p-3.5", className)} {...rest} />;
}
