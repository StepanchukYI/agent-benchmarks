import { StatusPill } from "../ui/StatusPill";
import type { ScorerKind } from "../../lib/types";

interface ScorerEntry {
  name: string;
  kind: ScorerKind | "ensemble";
  pass: boolean;
  detail: string;
}

const DEFAULT_CHAIN: ScorerEntry[] = [
  { name: "state_diff",          kind: "state_diff",     pass: true, detail: "Vault diff: +1 file, 0 deletions, 0 modifications" },
  { name: "schema(decision.v2)", kind: "schema",         pass: true, detail: "Frontmatter validates · all required keys present" },
  { name: "exec(linkcheck)",     kind: "exec",           pass: true, detail: "`supersedes: db-choice` → file exists" },
  { name: "privacy_check",       kind: "privacy_check",  pass: true, detail: "No matches in trajectory or vault diff" },
  { name: "llm_judge(3)",        kind: "ensemble",       pass: true, detail: "3/3 agree · mean score 0.91" },
];

interface ScorerVerdictPanelProps {
  scorers?: ScorerEntry[];
}

export function ScorerVerdictPanel({ scorers = DEFAULT_CHAIN }: ScorerVerdictPanelProps): JSX.Element {
  return (
    <div>
      {scorers.map((s, i) => (
        <div key={s.name} className={"py-2.5 " + (i > 0 ? "border-t border-border-soft" : "")}>
          <div className="flex items-center gap-2 mb-1">
            <StatusPill kind={s.pass ? "pass" : "fail"} size="sm">{s.pass ? "pass" : "fail"}</StatusPill>
            <span className="font-mono text-[11.5px] flex-1">{s.name}</span>
            <span className="text-muted-foreground text-[10.5px]">{s.kind}</span>
          </div>
          <div className="text-muted-foreground text-[11px] pl-0.5">{s.detail}</div>
        </div>
      ))}
    </div>
  );
}
