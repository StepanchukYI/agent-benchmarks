import { type ReactNode } from "react";
import { cn } from "../../lib/utils";

export interface Crumb {
  label: ReactNode;
  mono?: boolean;
  current?: boolean;
  href?: string;
}

export interface SubNavTab {
  id: string;
  label: ReactNode;
  count?: number;
  active?: boolean;
  onSelect?: () => void;
}

interface SubNavProps {
  crumbs?: Crumb[];
  tabs?: SubNavTab[];
  trailing?: ReactNode;
}

export function SubNav({ crumbs = [], tabs = [], trailing }: SubNavProps): JSX.Element {
  return (
    <div className="h-[42px] flex items-center gap-3 px-4 border-b border-border bg-background">
      {crumbs.length > 0 && (
        <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1.5">
              <span
                className={cn(
                  c.mono && "font-mono text-[12px]",
                  c.current && "text-foreground",
                )}
              >
                {c.label}
              </span>
              {i < crumbs.length - 1 && <span className="opacity-50">/</span>}
            </span>
          ))}
        </div>
      )}

      {tabs.length > 0 && (
        <div className="flex gap-0 ml-2">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={t.onSelect}
              className={cn(
                "h-7 px-3 inline-flex items-center gap-1.5 rounded-md text-[12px]",
                t.active
                  ? "text-foreground bg-panel-2 shadow-[inset_0_0_0_1px_hsl(var(--border))]"
                  : "text-muted-foreground hover:text-foreground hover:bg-panel-2",
              )}
            >
              {t.label}
              {t.count != null && (
                <span className="text-[10.5px] tnum px-1 py-[1px] rounded bg-panel-3 text-muted-foreground">
                  {t.count}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      <div className="flex-1" />
      {trailing}
    </div>
  );
}
