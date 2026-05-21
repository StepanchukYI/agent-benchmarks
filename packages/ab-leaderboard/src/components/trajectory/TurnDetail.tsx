import { useState } from "react";
import { Pill } from "../ui/Pill";
import { Callout } from "../ui/Callout";
import { Panel } from "../ui/Panel";
import { PillarRadar } from "../charts/PillarRadar";
import { ScorerVerdictPanel } from "./ScorerVerdictPanel";
import { CodeBlock, type Token } from "./CodeBlock";
import { DiffView, type DiffLine } from "./DiffView";
import { StatusPill } from "../ui/StatusPill";
import { MiniBar } from "../ui/MiniBar";
import { TRAJECTORY } from "../../lib/mock-data";
import type { TurnEvent, TrustTier } from "../../lib/types";
import { cn } from "../../lib/utils";

const TABS_FOR_KIND: Record<TurnEvent["kind"], string[]> = {
  prompt:  ["Prompt"],
  tool:    ["Tool call", "Tool return"],
  read:    ["Tool call", "Tool return"],
  write:   ["Vault diff", "Tool call"],
  thought: ["Output"],
  judge:   ["Judges"],
  verdict: ["Scorers", "Pillars"],
};

interface TurnDetailProps {
  turn: TurnEvent;
}

export function TurnDetail({ turn }: TurnDetailProps): JSX.Element {
  const tabs = TABS_FOR_KIND[turn.kind];
  const [tab, setTab] = useState<string>(tabs[0]!);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-border shrink-0">
        <span className="font-mono text-muted-foreground text-[11px]">
          #{String(turn.idx).padStart(2, "0")}
        </span>
        <span className="font-medium">{turn.label}</span>
        <Pill tone="neutral" size="sm" noDot>{turn.kind}</Pill>
        <div className="flex-1" />
        <nav className="flex">
          {tabs.map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                "h-7 px-3 inline-flex items-center text-[12px] rounded-md",
                tab === t
                  ? "text-foreground bg-panel-2 shadow-[inset_0_0_0_1px_hsl(var(--border))]"
                  : "text-muted-foreground hover:text-foreground hover:bg-panel-2",
              )}
            >
              {t}
            </button>
          ))}
        </nav>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {renderBody(turn, tab)}
      </div>
    </div>
  );
}

const PROMPT_TOKENS: Token[] = [
  { t: "c", v: "# System\n" },
  { t: "k", v: "You are" },
  { t: "p", v: " an expert vault editor. Follow the decision schema. Never delete existing files.\n\n" },
  { t: "c", v: "# Task\n" },
  { t: "k", v: "Goal" },
  { t: "p", v: ": " },
  { t: "s", v: '"Write a decision file capturing why we chose Postgres over SQLite for the v1 backend."' },
  { t: "p", v: "\n" },
  { t: "k", v: "Vault" },
  { t: "p", v: ": " },
  { t: "v", v: "fixture://vault-medium-2026-05" },
  { t: "p", v: "\n" },
  { t: "k", v: "Schema" },
  { t: "p", v: ": " },
  { t: "type", v: "schemas/decision.v2.json" },
  { t: "p", v: "\n" },
  { t: "k", v: "Acceptance" },
  { t: "p", v: ":\n  - " },
  { t: "s", v: '"Frontmatter validates"' },
  { t: "p", v: "\n  - " },
  { t: "s", v: '"Body has Context/Decision/Consequences sections"' },
  { t: "p", v: "\n  - " },
  { t: "s", v: '"No deletions in vault diff"' },
];

const PRIOR_FILE: DiffLine[] = [
  { kind: "ctx", text: "---" },
  { kind: "ctx", text: "title: DB choice deferred" },
  { kind: "ctx", text: "id: db-choice" },
  { kind: "del", text: "status: open" },
  { kind: "ctx", text: "decided_by: <user>" },
  { kind: "ctx", text: "decided_at: 2025-04-11" },
  { kind: "ctx", text: "---" },
  { kind: "ctx", text: "" },
  { kind: "ctx", text: "Deferring DB choice until we have a concrete dataset shape." },
  { kind: "ctx", text: "Will revisit once agent-benchmarks PRD is approved." },
];

const NEW_FILE: DiffLine[] = [
  { kind: "ctx", text: "---" },
  { kind: "add", text: "title: Postgres over SQLite for v1 backend" },
  { kind: "add", text: "id: postgres-vs-sqlite" },
  { kind: "add", text: "status: accepted" },
  { kind: "add", text: "decided_by: <user>" },
  { kind: "add", text: "decided_at: 2026-05-21" },
  { kind: "add", text: "supersedes: db-choice" },
  { kind: "add", text: "tags: [infrastructure, backend, agent-benchmarks]" },
  { kind: "ctx", text: "---" },
  { kind: "ctx", text: "" },
  { kind: "ctx", text: "## Context" },
  { kind: "ctx", text: "" },
  { kind: "add", text: "Agent-benchmarks needs to store trajectories, scorer verdicts, run metadata." },
  { kind: "add", text: "Single-user v1 — but P2.2 multi-tenant requires `tenant_id` on every row." },
  { kind: "add", text: "Variance comparisons need windowed aggregation (avg over N reruns)." },
  { kind: "ctx", text: "" },
  { kind: "ctx", text: "## Decision" },
  { kind: "ctx", text: "" },
  { kind: "add", text: "Adopt **Postgres 16** as the primary store. Run via docker-compose for dev," },
  { kind: "add", text: "managed (Neon / Supabase) for prod." },
  { kind: "ctx", text: "" },
  { kind: "ctx", text: "## Consequences" },
  { kind: "ctx", text: "" },
  { kind: "add", text: "+ Backups, point-in-time recovery come free." },
  { kind: "add", text: "+ Migration to multi-tenant later is a column rename, not a rewrite." },
  { kind: "add", text: "- Slightly heavier dev setup (no single-file db)." },
];

const JUDGES: Array<{ judge: string; verdict: TrustTier | "pass" | "fail"; score: number; reason: string }> = [
  { judge: "claude-opus-4-1",  verdict: "pass", score: 0.94, reason: "Frontmatter schema valid, three required sections present, ties to db-choice via supersedes." },
  { judge: "gpt-5",            verdict: "pass", score: 0.91, reason: "Decision is clearly motivated and consequences include rollback path." },
  { judge: "gemini-2.5-pro",   verdict: "pass", score: 0.88, reason: "Mild concern: consequences section could enumerate ops cost; not failing." },
];

function renderBody(turn: TurnEvent, tab: string): JSX.Element {
  if (turn.kind === "prompt") {
    return <CodeBlock header="system + task" lang="markdown" tokens={PROMPT_TOKENS} />;
  }
  if (turn.kind === "tool" || turn.kind === "read") {
    if (tab === "Tool return") {
      return (
        <CodeBlock
          header="return"
          lang="text"
          tokens={[{ t: "p", v: "14 files matched. (truncated mock)" }]}
        />
      );
    }
    return (
      <CodeBlock
        header={"call · " + turn.label.split("(")[0]}
        lang="json"
        tokens={[
          { t: "p", v: "{\n  " },
          { t: "type", v: '"pattern"' }, { t: "p", v: ": " }, { t: "s", v: '"**/decisions/*.md"' }, { t: "p", v: ",\n  " },
          { t: "type", v: '"case_sensitive"' }, { t: "p", v: ": " }, { t: "k", v: "false" },
          { t: "p", v: "\n}" },
        ]}
      />
    );
  }
  if (turn.kind === "write") {
    return (
      <DiffView
        beforeTitle="decisions/db-choice.md"
        afterTitle="decisions/postgres-vs-sqlite.md"
        before={PRIOR_FILE}
        after={NEW_FILE}
      />
    );
  }
  if (turn.kind === "thought") {
    return (
      <CodeBlock
        header="model output (chain-of-thought summary)"
        lang="text"
        tokens={[
          { t: "c", v: "[ summary of model reasoning ]\n\n" },
          { t: "p", v: "I should locate the existing db-choice decision file, read its current state, " },
          { t: "p", v: "then construct a new decision file that supersedes it. The new file needs:\n" },
          { t: "p", v: "  · frontmatter conforming to decision.v2.json\n" },
          { t: "p", v: "  · `supersedes: db-choice` so the link is bidirectional\n" },
          { t: "p", v: "  · Context / Decision / Consequences sections per template" },
        ]}
      />
    );
  }
  if (turn.kind === "judge") {
    return (
      <div className="flex flex-col gap-2.5">
        {JUDGES.map((j) => (
          <Panel key={j.judge} className="p-3.5 flex items-start gap-3.5">
            <div className="w-[130px] shrink-0">
              <div className="font-mono text-[12px] font-medium">{j.judge}</div>
              <div className="mt-1.5"><StatusPill kind="pass" size="sm">{j.verdict}</StatusPill></div>
              <div className="font-mono text-[11px] text-muted-foreground mt-1">score {j.score}</div>
            </div>
            <div className="flex-1 text-[12px] text-foreground-2 leading-relaxed">
              <span className="text-muted-foreground">rationale: </span>{j.reason}
            </div>
          </Panel>
        ))}
        <Callout tone="info">
          Ensemble verdict: <strong>pass</strong> · agreement κ = 1.00 · no human review needed
        </Callout>
      </div>
    );
  }
  if (turn.kind === "verdict") {
    if (tab === "Pillars") {
      return (
        <div className="flex justify-center"><PillarRadar scores={TRAJECTORY.pillar_scores} size={260} /></div>
      );
    }
    return (
      <div className="grid grid-cols-2 gap-5">
        <div>
          <div className="text-muted-foreground text-[10.5px] mb-2 tracking-wider">SCORER CHAIN — 5/5 PASS</div>
          <ScorerVerdictPanel />
        </div>
        <div>
          <div className="text-muted-foreground text-[10.5px] mb-2 tracking-wider">PILLAR SCORES</div>
          <div className="flex justify-center"><PillarRadar scores={TRAJECTORY.pillar_scores} size={220} /></div>
          <div className="grid grid-cols-2 gap-1.5 mt-3">
            {Object.entries(TRAJECTORY.pillar_scores).map(([k, v]) => (
              <div key={k} className="grid items-center gap-2" style={{ gridTemplateColumns: "1fr 50px 32px" }}>
                <span className="text-muted-foreground text-[11px]">{k}</span>
                <MiniBar value={v} tone={v > 85 ? "pass" : v > 70 ? "neutral" : "warn"} width="100%" />
                <span className="font-mono text-[11px] tnum font-semibold text-right">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }
  return <></>;
}
