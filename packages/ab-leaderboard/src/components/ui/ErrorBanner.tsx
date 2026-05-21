import { AlertTriangle } from "lucide-react";
import { Button } from "./Button";
import { cn } from "../../lib/utils";

export interface ErrorBannerProps {
  message: string;
  retry?: () => void;
  className?: string;
}

/**
 * Red-tinted strip shown when the API returned an error outside the
 * dev-mock fallback window (e.g. a real 5xx in production).
 */
export function ErrorBanner({ message, retry, className }: ErrorBannerProps): JSX.Element {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-center gap-2.5 rounded-md border border-fail/30 bg-fail/[0.08]",
        "px-3 py-2 text-[12px] text-fail",
        className,
      )}
    >
      <AlertTriangle className="size-3.5 shrink-0" aria-hidden />
      <span className="flex-1 min-w-0 truncate">{message}</span>
      {retry && (
        <Button size="sm" variant="destructive" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  );
}
