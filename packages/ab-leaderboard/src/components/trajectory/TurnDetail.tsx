import { useState } from "react";
import { Pill } from "../ui/Pill";
import { CodeBlock } from "./CodeBlock";
import { EmptyState } from "../ui/EmptyState";
import type { TrajectoryViewTurn, TurnEvent } from "../../lib/types";
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
  /** Timeline event — drives the header label + tabs (carries kind/label/meta). */
  event: TurnEvent;
  /** Rich turn content; undefined for scorer/judge/verdict events (no turn body). */
  turn: TrajectoryViewTurn | undefined;
}

/** Coerce an `unknown` payload field to displayable text without inventing structure. */
function asText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function TurnDetail({ event, turn }: TurnDetailProps): JSX.Element {
  const tabs = TABS_FOR_KIND[event.kind];
  const [tab, setTab] = useState<string>(tabs[0]!);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center gap-3 px-5 py-3 border-b border-border shrink-0">
        <span className="font-mono text-muted-foreground text-[11px]">
          #{String(event.idx).padStart(2, "0")}
        </span>
        <span className="font-medium">{event.label}</span>
        <Pill tone="neutral" size="sm" noDot>{event.kind}</Pill>
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
        {renderBody(event, tab, turn)}
      </div>
    </div>
  );
}

function renderBody(event: TurnEvent, tab: string, turn: TrajectoryViewTurn | undefined): JSX.Element {
  // Scorer-derived events (judge/verdict) have no turn body — their detail
  // lives in the ScorerVerdictPanel rendered elsewhere on the page.
  if (event.kind === "judge" || event.kind === "verdict") {
    return (
      <EmptyState
        title="No turn-level detail for this step."
        hint="Scorer and judge verdicts are shown in the scorer panel."
      />
    );
  }

  if (!turn) return <EmptyState title="No detail recorded for this turn." />;

  if (event.kind === "prompt" || event.kind === "thought") {
    return <CodeBlock header="model output" lang="text" tokens={[{ t: "p", v: asText(turn.model_output) || "—" }]} />;
  }

  if (event.kind === "tool" || event.kind === "read") {
    if (tab === "Tool return") {
      const ret = turn.tool_returns[0];
      const body = ret ? asText(ret.content) : "";
      return (
        <CodeBlock
          header={ret?.path ? `return · ${ret.path}` : "return"}
          lang="text"
          tokens={[{ t: "p", v: (body || "—") + (ret?.truncated ? "\n…(truncated)" : "") }]}
        />
      );
    }
    const call = turn.tool_calls[0];
    return (
      <CodeBlock
        header={call?.name ? `call · ${call.name}` : "call"}
        lang="json"
        tokens={[{ t: "p", v: (call ? asText(call.args) : "—") + (call?.truncated ? "\n…(truncated)" : "") }]}
      />
    );
  }

  if (event.kind === "write") {
    if (tab === "Tool call") {
      const call = turn.tool_calls[0];
      return (
        <CodeBlock
          header={call?.name ? `call · ${call.name}` : "call"}
          lang="json"
          tokens={[{ t: "p", v: call ? asText(call.args) : "—" }]}
        />
      );
    }
    return <CodeBlock header="vault diff" lang="diff" tokens={[{ t: "p", v: asText(turn.vault_state_diff) || "—" }]} />;
  }

  return <></>;
}
