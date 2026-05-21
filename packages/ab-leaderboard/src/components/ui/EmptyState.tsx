import { Inbox } from "lucide-react";
import { type ReactNode } from "react";
import { cn } from "../../lib/utils";

export interface EmptyStateProps {
  title: ReactNode;
  hint?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/**
 * Rendered when the live API returned successfully but the dataset is empty
 * (DB has no rows yet). Friendly + actionable — never silently substituted
 * with mock data.
 */
export function EmptyState({ title, hint, action, className }: EmptyStateProps): JSX.Element {
  return (
    <div
      role="status"
      className={cn(
        "flex flex-col items-center justify-center gap-2 text-center",
        "rounded-lg border border-dashed border-border bg-background-2",
        "text-muted-foreground px-6 py-8 min-h-[200px]",
        className,
      )}
    >
      <Inbox className="size-5 text-muted-foreground" aria-hidden />
      <div className="text-[12.5px] font-medium text-foreground-2">{title}</div>
      {hint != null && <div className="text-[11.5px] max-w-[420px]">{hint}</div>}
      {action != null && <div className="mt-1.5">{action}</div>}
    </div>
  );
}
