import { type ReactNode } from "react";
import { cn } from "../../lib/utils";

interface PageHeroProps {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/**
 * Page header strip. Sits between SubNav and the page content; renders title
 * + tagline on the left and a slot for run/refresh/launch buttons on the
 * right.
 */
export function PageHero({ title, subtitle, actions, className }: PageHeroProps): JSX.Element {
  return (
    <div
      className={cn(
        "px-6 pt-5 pb-3 flex items-end justify-between gap-6 border-b border-border-soft",
        className,
      )}
    >
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle != null && (
          <div className="text-[12.5px] text-muted-foreground max-w-prose mt-1">{subtitle}</div>
        )}
      </div>
      {actions != null && <div className="flex items-center gap-1.5">{actions}</div>}
    </div>
  );
}
