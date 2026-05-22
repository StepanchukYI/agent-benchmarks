import { AlertTriangle, TrendingUp } from "lucide-react";
import { Panel, PanelHeader } from "../ui/Panel";
import { Pill } from "../ui/Pill";
import { Avatar } from "../ui/Avatar";
import { EmptyState } from "../ui/EmptyState";
import { ErrorBanner } from "../ui/ErrorBanner";
import { LoadingSkeleton } from "../ui/LoadingSkeleton";
import type { RegressionItem } from "../../lib/types";
import { useOperators } from "../../api/hooks";

interface HotListProps {
  title?: string;
  kind: "regression" | "improvement";
  items: RegressionItem[];
  /** When provided, the list renders a loading / empty / error state instead
   *  of the row list while the data isn't ready. */
  state?: "loading" | "empty" | "ok" | "error";
  errorMessage?: string;
  onRetry?: () => void;
}

export function HotList({
  title,
  kind,
  items,
  state = "ok",
  errorMessage,
  onRetry,
}: HotListProps): JSX.Element {
  const isReg = kind === "regression";
  const head = title ?? (isReg ? "Top regressions" : "Top improvements");
  const Icon = isReg ? AlertTriangle : TrendingUp;
  const { data: operators } = useOperators();
  const operatorList = operators ?? [];
  return (
    <Panel>
      <PanelHeader
        title={
          <span className={"inline-flex items-center gap-1.5 " + (isReg ? "text-fail" : "text-pass")}>
            <Icon className="size-3" />
            {head}
          </span>
        }
      />
      {state === "loading" && (
        <div className="p-3.5"><LoadingSkeleton rows={4} columns={1} /></div>
      )}
      {state === "error" && (
        <div className="p-3.5">
          <ErrorBanner message={errorMessage ?? "Failed to load."} retry={onRetry} />
        </div>
      )}
      {state === "empty" && (
        <div className="p-3.5">
          <EmptyState
            title={isReg ? "No regressions in the window." : "No improvements logged yet."}
            hint={
              isReg
                ? "Drift detection compares each suite's last 7d window against the previous 7d."
                : "Improvements appear once a model's correctness rises > 1% week-over-week."
            }
          />
        </div>
      )}
      {state === "ok" && (
        <ul>
          {items.map((r, i) => {
            const op = operatorList.find((o) => o.handle === r.operator);
            const isSelf = op?.is_self ?? false;
            const sign = r.delta_pct > 0 ? "▲" : "▼";
            const value = Math.abs(r.delta_pct).toFixed(1);
            const color = isReg
              ? isSelf ? "text-fail" : "text-warn"
              : "text-pass";
            return (
              <li
                key={r.model + r.suite}
                className={"flex items-center gap-2.5 px-3.5 py-2.5 " + (i > 0 ? "border-t border-border-soft" : "")}
              >
                {op && <Avatar operator={op} size={18} />}
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-[11.5px] font-medium flex items-center gap-1.5">
                    {r.model}
                    {isReg && !isSelf && (
                      <Pill tone="neutral" size="sm" noDot className="text-[9px] px-1">friend</Pill>
                    )}
                  </div>
                  <div className="text-muted-foreground text-[11px]">
                    {r.suite} · {r.window_days}d · @{r.operator}
                  </div>
                </div>
                <span className={"font-semibold tnum " + color}>
                  {sign}{value}%
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
