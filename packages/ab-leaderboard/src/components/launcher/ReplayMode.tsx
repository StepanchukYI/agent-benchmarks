import { Github, Info, RotateCcw } from "lucide-react";
import { useState } from "react";
import { Panel, PanelHeader, PanelBody } from "../ui/Panel";
import { Button } from "../ui/Button";
import { Callout } from "../ui/Callout";
import { CheckBox } from "../ui/CheckBox";
import { Tag } from "../ui/Tag";
import { Avatar } from "../ui/Avatar";
import { useOperators } from "../../api/hooks";

interface RecentCommit {
  repo: string;
  sha: string;
  run_id: string;
  model: string;
  suite: string;
  when: string;
}

const RECENT: RecentCommit[] = [
  { repo: "rachel-yeh/ab-runs",         sha: "3f81e44", run_id: "ab-2026-21-12", model: "gpt-5",              suite: "L1_memory_write", when: "2h ago" },
  { repo: "noamb/agent-bench-results",  sha: "b240cf6", run_id: "ab-2026-20-06", model: "gemini-2.5-pro",     suite: "L2_mcp",          when: "14h ago" },
  { repo: "djun-kim/agent-bench",       sha: "7b3d551", run_id: "ab-2026-21-04", model: "claude-opus-4-1",    suite: "L1_retrieval",    when: "4h ago" },
  { repo: "kpyrne/ab-eval",             sha: "c8e4a12", run_id: "ab-2026-19-19", model: "glm-4-6",            suite: "L0+L1",           when: "2d ago" },
];

function ownerOf(repo: string): string {
  return repo.split("/")[0] ?? "";
}

export function ReplayMode(): JSX.Element {
  const [url, setUrl] = useState("");
  const [picked, setPicked] = useState<number | null>(null);
  const { data: operators } = useOperators();
  const operatorList = operators ?? [];

  return (
    <Panel>
      <PanelHeader title="Replay from a connected repo" hint="re-runs the exact trajectory" />
      <PanelBody className="flex flex-col gap-4">
        <div>
          <div className="text-[11.5px] font-medium mb-1.5">Paste a GitHub commit URL</div>
          <div className="flex gap-1.5">
            <div className="flex-1 relative">
              <Github className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="h-7 w-full pl-8 pr-2 rounded-md border border-border bg-panel-2 font-mono text-[12px] placeholder:text-muted-foreground"
                placeholder="github.com/<handle>/repo/commit/<sha>/run/<id>"
              />
            </div>
            <Button>Validate</Button>
          </div>
          <div className="text-[11px] text-muted-foreground mt-1">
            Fetches the trajectory, fixtures, and scorer chain pinned to that commit.
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-[11.5px] font-medium">
              Or pick from connected repos
              <span className="text-muted-foreground"> · 6 connected</span>
            </div>
            <Button size="sm" variant="ghost">Manage repos →</Button>
          </div>
          <div className="rounded-lg border border-border overflow-hidden">
            {RECENT.map((r, i) => {
              const op = operatorList.find((o) => o.handle === ownerOf(r.repo));
              const isSel = picked === i;
              return (
                <button
                  type="button"
                  key={r.repo + r.sha}
                  onClick={() => setPicked(i)}
                  className={
                    "w-full grid items-center gap-2.5 px-3 py-2.5 text-left " +
                    (i < RECENT.length - 1 ? "border-b border-border-soft " : "") +
                    (isSel ? "bg-accent/[0.12]" : "hover:bg-panel-2")
                  }
                  style={{ gridTemplateColumns: "24px 1fr 130px 130px 70px" }}
                >
                  <CheckBox checked={isSel} />
                  <div className="flex items-center gap-2 min-w-0">
                    {op && <Avatar operator={op} size={16} />}
                    <span className="font-mono text-[11.5px] truncate">github.com/{r.repo}</span>
                    <Tag>{r.sha}</Tag>
                  </div>
                  <span className="font-mono text-[11px] text-foreground-2">{r.model}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">{r.suite}</span>
                  <span className="text-[11px] text-muted-foreground">{r.when}</span>
                </button>
              );
            })}
          </div>
        </div>

        {picked != null && (
          <div className="grid grid-cols-3 gap-3.5 p-3.5 bg-background-2 rounded-lg border border-border">
            <Locked label="MODEL" value={RECENT[picked]!.model} />
            <Locked label="SUITE" value={RECENT[picked]!.suite} />
            <Locked label="SCORER" value="state_diff + llm_judge(3)" />
          </div>
        )}

        <Callout tone="accent" icon={<Info className="size-3.5" />}>
          Replay re-fetches the exact fixture, scorer chain and model versions pinned at the commit.
          Useful for verifying a peer's result or doing a fixture-level diff.
        </Callout>

        <div className="flex items-center justify-between border-t border-border-soft pt-3.5 -mt-1">
          <div className="text-muted-foreground text-[11px]">
            You may optionally swap the model for one of your own to compare.
          </div>
          <div className="flex gap-2">
            <Button>Swap model…</Button>
            <Button variant="primary" size="lg" disabled={picked == null}>
              <RotateCcw className="size-3.5" /> Replay
            </Button>
          </div>
        </div>
      </PanelBody>
    </Panel>
  );
}

function Locked({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <div className="text-[10.5px] text-muted-foreground tracking-wider">{label} (locked)</div>
      <div className="font-mono text-[12px] mt-0.5">{value}</div>
    </div>
  );
}
