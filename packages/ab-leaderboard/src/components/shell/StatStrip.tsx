import { type ReactNode } from "react";
import { cn } from "../../lib/utils";
import { deltaTone } from "../../lib/format";

export interface Stat {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  delta?: ReactNode;
  /** Affects delta color. */
  deltaValue?: number | null;
}

interface StatStripProps {
  stats: Stat[];
  className?: string;
}

export function StatStrip({ stats, className }: StatStripProps): JSX.Element {
  return (
    <div className={cn("flex border-t border-b border-border-soft", className)}>
      {stats.map((s, i) => {
        const tone = deltaTone(s.deltaValue);
        return (
          <div key={i} className="flex-1 px-5 py-3 border-r border-border-soft last:border-r-0">
            <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
              {s.label}
            </div>
            <div className="text-[18px] font-semibold tnum mt-1 tracking-tight">
              {s.value}
              {s.unit != null && (
                <span className="text-[11px] text-muted-foreground font-normal ml-1">{s.unit}</span>
              )}
            </div>
            {s.delta != null && (
              <div
                className={cn(
                  "text-[11px] tnum mt-0.5",
                  tone === "up" && "text-pass",
                  tone === "dn" && "text-fail",
                  tone === "flat" && "text-muted-foreground",
                )}
              >
                {s.delta}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
