import { Search } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Avatar } from "../ui/Avatar";
import { CheckBox } from "../ui/CheckBox";
import { Button } from "../ui/Button";
import { TrustDot } from "../domain/TrustDot";
import { useModels, useOperators, useSuites } from "../../api/hooks";
import { cn } from "../../lib/utils";

export interface LeaderboardFilters {
  suites: string[];
  models: string[];
  operators: string[];
  trustTiers: ("official" | "verified" | "self_reported")[];
  datasetCurrentOnly: boolean;
  dateRange: "24h" | "7d" | "30d" | "90d";
}

interface FilterRailProps {
  filters: LeaderboardFilters;
  setFilters: (next: LeaderboardFilters) => void;
}

export function FilterRail({ filters, setFilters }: FilterRailProps): JSX.Element {
  const [search, setSearch] = useState("");
  const { data: models } = useModels();
  const { data: operators } = useOperators();
  const { data: suites } = useSuites();
  const modelList = models ?? [];
  const operatorList = operators ?? [];
  const suiteList = suites ?? [];

  function toggle<K extends keyof LeaderboardFilters>(key: K, value: string): void {
    const cur = filters[key] as unknown as string[];
    const next = cur.includes(value) ? cur.filter((x) => x !== value) : [...cur, value];
    setFilters({ ...filters, [key]: next });
  }

  return (
    <aside className="w-[240px] shrink-0 border-r border-border bg-background-2 overflow-y-auto">
      <div className="px-3.5 pt-3.5 pb-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter models, suites…"
            className="h-7 w-full pl-7 pr-2 rounded-md border border-border bg-panel-2 text-[12px] placeholder:text-muted-foreground focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
        </div>
      </div>

      <Group title="Operator">
        {operatorList.map((op) => (
          <Row
            key={op.handle}
            on={filters.operators.includes(op.handle)}
            onClick={() => toggle("operators", op.handle)}
            label={
              <span className="flex items-center gap-1.5">
                <Avatar operator={op} size={14} />
                <span className={cn("font-mono text-[11.5px]", op.is_self && "font-semibold")}>
                  @{op.handle}
                </span>
              </span>
            }
            count={op.is_self ? 412 : Math.floor(40 + ((op.handle.length * 13) % 150))}
          />
        ))}
      </Group>

      <Group title="Trust tier">
        <Row
          on={filters.trustTiers.includes("official")}
          onClick={() => toggle("trustTiers", "official")}
          label={<><TrustDot tier="official" size={10} /> Official</>}
          count={3}
        />
        <Row
          on={filters.trustTiers.includes("verified")}
          onClick={() => toggle("trustTiers", "verified")}
          label={<><TrustDot tier="verified" size={10} /> Verified</>}
          count={9}
        />
        <Row
          on={filters.trustTiers.includes("self_reported")}
          onClick={() => toggle("trustTiers", "self_reported")}
          label={<><TrustDot tier="self_reported" size={10} /> Self-reported</>}
          count={42}
        />
      </Group>

      <Group title="Dataset version">
        <Row
          on={filters.datasetCurrentOnly}
          onClick={() => setFilters({ ...filters, datasetCurrentOnly: !filters.datasetCurrentOnly })}
          label="≥ current (v1.0)"
          count={132}
        />
        <Row
          on={!filters.datasetCurrentOnly}
          onClick={() => setFilters({ ...filters, datasetCurrentOnly: false })}
          label="any version"
          count={159}
        />
      </Group>

      <Group title="Suite" action="Clear">
        {suiteList.map((s) => (
          <Row
            key={s.id}
            on={filters.suites.includes(s.id)}
            onClick={() => toggle("suites", s.id)}
            label={`${s.layer} · ${s.name}`}
            count={s.task_count}
          />
        ))}
      </Group>

      <Group title="Model">
        {modelList.map((m) => (
          <Row
            key={m.id}
            on={filters.models.includes(m.id)}
            onClick={() => toggle("models", m.id)}
            label={m.id}
            count={Math.floor(40 + ((m.id.length * 11) % 60))}
          />
        ))}
      </Group>

      <Group title="Date range">
        <div className="px-3.5 py-1.5">
          <div className="flex gap-1">
            {(["24h", "7d", "30d", "90d"] as const).map((r) => (
              <Button
                key={r}
                size="sm"
                variant={filters.dateRange === r ? "primary" : "default"}
                className="flex-1 justify-center"
                onClick={() => setFilters({ ...filters, dateRange: r })}
              >
                {r}
              </Button>
            ))}
          </div>
        </div>
      </Group>
    </aside>
  );
}

function Group({ title, action, children }: { title: string; action?: string; children: ReactNode }): JSX.Element {
  return (
    <div className="border-b border-border-soft pb-2.5 last:border-b-0">
      <div className="px-3.5 pt-3 pb-1.5 flex items-center justify-between text-[10.5px] uppercase tracking-wider font-semibold text-muted-foreground">
        <span>{title}</span>
        {action && (
          <button className="text-[11px] font-normal normal-case tracking-normal text-muted-foreground hover:text-foreground">
            {action}
          </button>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

function Row({
  on,
  label,
  count,
  onClick,
}: {
  on?: boolean;
  label: ReactNode;
  count?: number;
  onClick?: () => void;
}): JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center gap-2 px-3.5 py-1 text-[12px] text-foreground-2 hover:bg-panel-2"
    >
      <CheckBox checked={!!on} />
      <span className="flex-1 text-left">{label}</span>
      {count != null && <span className="text-muted-foreground text-[11px] tnum">{count}</span>}
    </button>
  );
}
