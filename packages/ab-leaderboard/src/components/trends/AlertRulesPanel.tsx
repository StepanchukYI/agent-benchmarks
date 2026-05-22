import { Plus } from "lucide-react";
import { Panel, PanelHeader } from "../ui/Panel";
import { Button } from "../ui/Button";
import { StatusPill } from "../ui/StatusPill";
import { Tag } from "../ui/Tag";
import { EmptyState } from "../ui/EmptyState";
import { ErrorBanner } from "../ui/ErrorBanner";
import { LoadingSkeleton } from "../ui/LoadingSkeleton";
import { useAlertRules } from "../../api/hooks";
import { toState } from "../../lib/ui-state";

interface AlertRulesPanelProps {
  /** Opens the full Alerts tab where the create form lives. */
  onNewRule?: () => void;
}

export function AlertRulesPanel({ onNewRule }: AlertRulesPanelProps): JSX.Element {
  const alertsQuery = useAlertRules();
  const state = toState(alertsQuery);
  return (
    <Panel>
      <PanelHeader
        title="Active alert rules"
        actions={<Button size="sm" onClick={onNewRule}><Plus className="size-3" /> New rule</Button>}
      />
      <div className="p-3.5 flex flex-col gap-2.5">
        {state.kind === "loading" && <LoadingSkeleton rows={3} columns={1} />}
        {state.kind === "error" && (
          <ErrorBanner message={state.message} retry={() => alertsQuery.refetch()} />
        )}
        {state.kind === "empty" && (
          <EmptyState
            title="No alert rules configured."
            hint={
              <>
                Add a rule with{" "}
                <span className="font-mono text-foreground-2">ab alerts add</span>{" "}
                or use the New rule button.
              </>
            }
          />
        )}
        {state.kind === "ok" && state.value.map((r) => (
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
