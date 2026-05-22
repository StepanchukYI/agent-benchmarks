import { StatusPill } from "../ui/StatusPill";
import { EmptyState } from "../ui/EmptyState";
import { fmtScore } from "../../lib/format";
import type { TrajectoryViewScorer } from "../../lib/types";

function detailText(detail: unknown): string {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  try {
    return JSON.stringify(detail);
  } catch {
    return String(detail);
  }
}

interface ScorerVerdictPanelProps {
  scorers: TrajectoryViewScorer[];
}

export function ScorerVerdictPanel({ scorers }: ScorerVerdictPanelProps): JSX.Element {
  if (scorers.length === 0) {
    return <EmptyState title="No scorer verdicts for this run." />;
  }

  return (
    <div>
      {scorers.map((s, i) => {
        const name = s.scorer_name ?? s.kind ?? "scorer";
        const pass = s.pass === true;
        return (
          <div key={`${name}-${i}`} className={"py-2.5 " + (i > 0 ? "border-t border-border-soft" : "")}>
            <div className="flex items-center gap-2 mb-1">
              <StatusPill kind={s.pass == null ? "idle" : pass ? "pass" : "fail"} size="sm">
                {s.pass == null ? "n/a" : pass ? "pass" : "fail"}
              </StatusPill>
              <span className="font-mono text-[11.5px] flex-1">{name}</span>
              {s.score != null && (
                <span className="font-mono text-[10.5px] text-muted-foreground">{fmtScore(s.score)}</span>
              )}
              {s.kind && <span className="text-muted-foreground text-[10.5px]">{s.kind}</span>}
            </div>
            {detailText(s.detail) && (
              <div className="text-muted-foreground text-[11px] pl-0.5">{detailText(s.detail)}</div>
            )}
          </div>
        );
      })}
    </div>
  );
}
