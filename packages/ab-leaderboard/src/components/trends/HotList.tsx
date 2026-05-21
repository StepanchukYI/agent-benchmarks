import { AlertTriangle, ChevronRight, TrendingUp } from "lucide-react";
import { Panel, PanelHeader } from "../ui/Panel";
import { Pill } from "../ui/Pill";
import { Button } from "../ui/Button";
import { Avatar } from "../ui/Avatar";
import type { RegressionItem } from "../../lib/types";
import { operatorByHandle } from "../../lib/mock-data";

interface HotListProps {
  title?: string;
  kind: "regression" | "improvement";
  items: RegressionItem[];
}

export function HotList({ title, kind, items }: HotListProps): JSX.Element {
  const isReg = kind === "regression";
  const head = title ?? (isReg ? "Top regressions" : "Top improvements");
  const Icon = isReg ? AlertTriangle : TrendingUp;
  return (
    <Panel>
      <PanelHeader
        title={
          <span className={"inline-flex items-center gap-1.5 " + (isReg ? "text-fail" : "text-pass")}>
            <Icon className="size-3" />
            {head}
          </span>
        }
        actions={<Button size="sm" variant="ghost">All →</Button>}
      />
      <ul>
        {items.map((r, i) => {
          const op = operatorByHandle(r.operator);
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
              <Button size="icon-sm" variant="ghost"><ChevronRight className="size-3" /></Button>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
