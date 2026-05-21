import { Plus } from "lucide-react";
import { Panel, PanelHeader } from "../ui/Panel";
import { Button } from "../ui/Button";
import { StatusPill } from "../ui/StatusPill";
import { Tag } from "../ui/Tag";
import { useAlertRules } from "../../api/hooks";

export function AlertRulesPanel(): JSX.Element {
  const { data: alertRules } = useAlertRules();
  const rules = alertRules ?? [];
  return (
    <Panel>
      <PanelHeader
        title="Active alert rules"
        actions={<Button size="sm"><Plus className="size-3" /> New rule</Button>}
      />
      <div className="p-3.5 flex flex-col gap-2.5">
        {rules.map((r) => (
          <div key={r.name} className="p-3 rounded-md border border-border bg-panel-2">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-[12px]">{r.name}</span>
              <span className="flex-1" />
              <StatusPill kind={r.status === "fired" ? "warn" : "idle"} size="sm">
                {r.status === "fired" ? `fired ${r.last_fired_relative ?? ""}`.trim() : r.status}
              </StatusPill>
            </div>
            <div className="font-mono text-[11px] text-foreground-2 mt-1">{r.condition}</div>
            <div className="flex items-center gap-1.5 mt-1.5 text-[10.5px]">
              <span className="text-muted-foreground">target {r.target}</span>
              <span className="flex-1" />
              {r.actions.map((a) => <Tag key={a}>{a}</Tag>)}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}
