import { Check, ChevronDown, ChevronRight, Download, Filter } from "lucide-react";
import { useState, type TdHTMLAttributes, type ThHTMLAttributes } from "react";
import { Panel, PanelHeader } from "../ui/Panel";
import { Button } from "../ui/Button";
import { Tag } from "../ui/Tag";
import { Sparkline } from "../ui/Sparkline";
import { ModelCell } from "../domain/ModelCell";
import { OperatorTag } from "../domain/OperatorTag";
import { ScoreCell } from "../domain/ScoreCell";
import { StaleDatasetPill } from "../domain/StaleDatasetPill";
import { TrustDot } from "../domain/TrustDot";
import { StatusPill } from "../ui/StatusPill";
import { EmptyState } from "../ui/EmptyState";
import { PILLARS } from "../../lib/mock-data";
import { useLeaderboard, useModels, useRowTaskDrill, useTrendsSeries } from "../../api/hooks";
import { fmtMoney, fmtScore } from "../../lib/format";
import { toState } from "../../lib/ui-state";
import { cn } from "../../lib/utils";
import type { LeaderboardRow, Model } from "../../lib/types";

const VENDOR_HEX: Record<string, string> = {
  anthropic: "#d97757",
  openai: "#10a37f",
  google: "#4285f4",
  zhipu: "#8b5cf6",
  minimax: "#f59e0b",
};

type SortDir = "asc" | "desc";
interface Sort { key: number; dir: SortDir; }

/** PILLARS index of the Context pillar — shows real token usage, not a score. */
const CONTEXT_PILLAR_IDX = 1;

/** Native title= tooltip explaining what each pillar column measures. */
const PILLAR_TOOLTIP: Record<string, string> = {
  Correctness: "Quality score (0–100): mean over Correctness scorers. Not a task pass-rate.",
  Context: "Median tokens per task. Not a 0–100 score — lower is more token-efficient.",
  "Tool/Skill": "Quality score (0–100): mean over Tool/Skill scorers. Not a task pass-rate.",
  Memory: "Quality score (0–100): mean over Memory scorers. Not a task pass-rate.",
  Cost: "Speed score (0–100): full marks under ~10s, decaying to 0 by ~120s. Cost only counts when a task sets a max budget.",
};

/** Median tokens/task as "12,400 tok"; "—" when unmeasured (0). */
function fmtTokens(n: number | null | undefined): string {
  if (n == null || n === 0) return "—";
  return `${n.toLocaleString("en-US")} tok`;
}

/** Stable row key for expand state — includes harness+effort so per-config rows stay distinct. */
function rowKey(r: LeaderboardRow): string {
  return `${r.model}/${r.operator}/${r.tier}/${r.harness ?? ""}/${r.effort ?? ""}`;
}

/**
 * Build the muted config chip label: "harness · effort · tier".
 * NULL-SAFE: parts that are null are omitted; tier always renders.
 */
function buildConfigChip(r: LeaderboardRow): string {
  const parts: string[] = [];
  if (r.harness != null) parts.push(r.harness);
  if (r.effort != null) parts.push(r.effort);
  parts.push(r.tier);
  return parts.join(" · ");
}

export function LeaderboardMatrix(): JSX.Element {
  const [sort, setSort] = useState<Sort>({ key: 0, dir: "desc" });
  const [hiddenPillars, setHiddenPillars] = useState<Set<number>>(new Set());
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const { data: leaderboard } = useLeaderboard({});
  const { data: models } = useModels();
  const { data: trendsSeries } = useTrendsSeries("30d");

  const rows = leaderboard?.rows ?? [];
  const pillars = leaderboard?.pillars ?? PILLARS;
  const modelList: Model[] = models ?? [];
  const trends: Record<string, (number | null)[]> = trendsSeries?.per_model ?? {};
  const operatorCount = new Set(rows.map((r) => r.operator)).size;

  const sorted = [...rows].sort((a, b) => {
    const sgn = sort.dir === "desc" ? -1 : 1;
    if (sort.key === -1) return sgn * a.model.localeCompare(b.model);
    if (sort.key === -2) return sgn * ((a.pass_rate ?? -1) - (b.pass_rate ?? -1));
    return sgn * ((a.scores[sort.key] ?? 0) - (b.scores[sort.key] ?? 0));
  });

  function toggleSort(key: number): void {
    setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }));
  }

  function togglePillar(idx: number): void {
    setHiddenPillars((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  }

  function exportCsv(): void {
    const header = ["model", "operator", "pass_rate_pct", ...pillars, "sweep_cost_usd"];
    const escape = (v: string): string =>
      /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
    const lines = sorted
      .filter((r) => modelList.some((m) => m.id === r.model))
      .map((r) =>
        [
          r.model,
          r.operator,
          r.pass_rate == null ? "" : String(r.pass_rate),
          ...r.scores.map((s) => (s == null ? "" : String(s))),
          r.sweep_cost == null ? "" : String(r.sweep_cost),
        ]
          .map((c) => escape(String(c)))
          .join(","),
      );
    const csv = [header.map(escape).join(","), ...lines].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "leaderboard.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        title="Per-pillar scores"
        hint={`${rows.length} ${rows.length === 1 ? "model" : "models"} × ${pillars.length} pillars · ${operatorCount} ${operatorCount === 1 ? "operator" : "operators"}`}
        actions={
          <>
            <div className="relative">
              <Button
                size="sm"
                variant={hiddenPillars.size ? "primary" : "default"}
                onClick={() => setColumnsOpen((v) => !v)}
              >
                <Filter className="size-3" /> Columns
              </Button>
              {columnsOpen && (
                <div className="absolute right-0 top-full mt-1 z-20 w-[200px] rounded-md border border-border bg-panel shadow-xl p-1">
                  {pillars.map((p, i) => {
                    const visible = !hiddenPillars.has(i);
                    return (
                      <button
                        key={p}
                        type="button"
                        onClick={() => togglePillar(i)}
                        className="w-full flex items-center gap-2 px-2 py-1.5 text-[12px] text-left rounded hover:bg-panel-2"
                      >
                        <span className="size-3.5 grid place-items-center">
                          {visible && <Check className="size-3 text-accent" />}
                        </span>
                        <span className="flex-1">{p}</span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
            <Button size="sm" variant="default" onClick={exportCsv}>
              <Download className="size-3" /> Export CSV
            </Button>
          </>
        }
      />
      <div className="overflow-x-auto">
        <table className="w-full text-[12.5px] border-collapse">
          <thead>
            <tr>
              {/* Chevron expand column — no label, fixed narrow width. */}
              <Th className="w-[32px] pl-2" />
              <Th onClick={() => toggleSort(-1)} active={sort.key === -1} dir={sort.dir} sticky className="pl-4 w-[280px]">
                Model
              </Th>
              <Th className="w-[170px]">Operator</Th>
              <Th onClick={() => toggleSort(-2)} active={sort.key === -2} dir={sort.dir} numeric className="w-[100px]" title="% of measured tasks where every scorer passed. The honest binary success rate.">
                % passed
              </Th>
              {pillars.map((p, i) =>
                hiddenPillars.has(i) ? null : (
                  <Th key={p} onClick={() => toggleSort(i)} active={sort.key === i} dir={sort.dir} numeric className="w-[120px]" title={PILLAR_TOOLTIP[p]}>
                    {p}
                  </Th>
                ),
              )}
              <Th className="w-[100px]" numeric>7d trend</Th>
              <Th className="w-[80px]" numeric>$/sweep</Th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => {
              const m = modelList.find((x) => x.id === r.model);
              if (!m) return null;
              const key = rowKey(r);
              const isExpanded = expandedRow === key;
              // +1 for chevron col, +1 for operator, +1 for pass_rate, +2 for trend+cost
              const colSpan = 5 + pillars.filter((_, idx) => !hiddenPillars.has(idx)).length;
              return (
                <>
                  <tr key={key} className="hover:bg-panel-2/50">
                    <Td className="pl-2">
                      <button
                        type="button"
                        aria-label={isExpanded ? "Collapse row" : "Expand row"}
                        onClick={() => setExpandedRow(isExpanded ? null : key)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        {isExpanded
                          ? <ChevronDown className="size-3.5" />
                          : <ChevronRight className="size-3.5" />}
                      </button>
                    </Td>
                    <Td className="pl-4">
                      <div className="flex items-center gap-2.5">
                        <span className="w-[18px] text-muted-foreground text-[11px] tnum">{i + 1}</span>
                        <ModelCell model={m} configChip={buildConfigChip(r)} />
                        <span className="flex gap-1">
                          <Tag>{m.capabilities[0]}</Tag>
                        </span>
                      </div>
                    </Td>
                    <Td>
                      <div className="flex flex-col gap-1 items-start">
                        <OperatorTag handle={r.operator} avatarSize={16} />
                        <StaleDatasetPill pin={r.dataset_pin} />
                      </div>
                    </Td>
                    <Td numeric className="pr-4 font-semibold">
                      {r.pass_rate == null ? "—" : `${r.pass_rate.toFixed(1)}%`}
                    </Td>
                    {r.scores.map((s, idx) =>
                      hiddenPillars.has(idx) ? null : idx === CONTEXT_PILLAR_IDX ? (
                        // Context column shows ACTUAL median tokens/task, not the
                        // synthetic 0..100 efficiency score (product-owner ask).
                        <Td key={idx} numeric className="pr-4 font-mono text-muted-foreground">
                          {fmtTokens(r.tokens_total)}
                        </Td>
                      ) : (
                        <Td key={idx} numeric className="pr-4">
                          <span className="inline-flex items-center gap-0.5">
                            <ScoreCell score={s} delta={r.delta[idx]} />
                            {idx === 0 && <TrustDot tier={r.trust_tier} commit={r.source_commit_sha} size={10} />}
                          </span>
                          {r.pillar_counts[idx] != null && r.pillar_counts[idx] > 0 && (
                            <span className="block text-right text-[10px] text-muted-foreground/60 tnum">
                              n={r.pillar_counts[idx]}
                            </span>
                          )}
                        </Td>
                      ),
                    )}
                    <Td numeric className="pr-4">
                      <Sparkline
                        data={(trends[r.model] ?? []).filter((v): v is number => v != null)}
                        width={84}
                        height={20}
                        color={VENDOR_HEX[m.vendor]}
                        fill
                        ariaLabel={`${m.short} 7-day correctness trend`}
                      />
                    </Td>
                    <Td numeric className="pr-4 font-mono">{fmtMoney(r.sweep_cost)}</Td>
                  </tr>
                  {isExpanded && (
                    <tr key={`${key}__drill`}>
                      <td colSpan={colSpan} className="bg-panel-2/40 border-b border-border-soft px-5 py-3">
                        <RowDrillPanel model={r.model} operator={r.operator} tier={r.tier} harness={r.harness} effort={r.effort} />
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

/* ─── Row drill panel ─────────────────────────────────────────────────────── */

interface RowDrillPanelProps {
  model: string;
  operator: string;
  tier: string;
  /** Null-safe — omitted from query when null (backend behavior TBD). */
  harness: string | null;
  /** Null-safe — omitted from query when null (backend behavior TBD). */
  effort: string | null;
}

/**
 * Per-row task drill panel. Fetches `GET /leaderboard/row/tasks` with the row's
 * exact (model, operator, tier, harness, effort) — operator is passed verbatim
 * per backend contract. harness/effort are threaded when non-null; null params
 * are omitted (withQuery skips null values). null-verdict rows render neutral
 * "not measured", never "fail".
 */
function RowDrillPanel({ model, operator, tier, harness, effort }: RowDrillPanelProps): JSX.Element {
  const drillKey = { model, operator, tier, harness, effort };
  const drillQuery = useRowTaskDrill(drillKey);
  const state = toState(drillQuery);

  if (state.kind === "loading") {
    return <span className="text-[11px] text-muted-foreground">Loading…</span>;
  }
  if (state.kind === "error") {
    return <span className="text-[11px] text-fail">{state.message}</span>;
  }
  if (state.kind === "empty") {
    return <EmptyState title="No task results for this row." />;
  }

  const items = state.value;
  return (
    <div className="flex flex-col gap-2">
      {items.map((item) => (
        <div key={item.task_id} className="rounded-md border border-border bg-panel px-3 py-2">
          <div className="flex items-center gap-2 mb-1.5">
            <StatusPill kind={item.passed == null ? "idle" : item.passed ? "pass" : "fail"} size="sm">
              {item.passed == null ? "not measured" : item.passed ? "pass" : "fail"}
            </StatusPill>
            <span className="font-mono text-[11.5px] font-medium">{item.task_id}</span>
            <span className="text-[10.5px] text-muted-foreground">{item.suite}</span>
          </div>
          {item.scorers.length > 0 ? (
            // (a) scorers non-empty → per-scorer breakdown.
            <div className="flex flex-col gap-0.5 pl-1">
              {item.scorers.map((s, si) => (
                <div key={`${s.name}-${si}`} className="flex items-center gap-2 text-[11px]">
                  <StatusPill kind={s.pass == null ? "idle" : s.pass ? "pass" : "fail"} size="sm">
                    {s.pass == null ? "—" : s.pass ? "pass" : "fail"}
                  </StatusPill>
                  <span className="font-mono text-muted-foreground flex-1">{s.name}</span>
                  {s.score != null && (
                    <span className="tnum text-muted-foreground">{fmtScore(s.score)}</span>
                  )}
                  {s.detail != null && (
                    <span className="text-muted-foreground/70 truncate max-w-[320px]">
                      {typeof s.detail === "string" ? s.detail : JSON.stringify(s.detail)}
                    </span>
                  )}
                </div>
              ))}
            </div>
          ) : item.passed != null ? (
            // (b) scorers [] but passed verdict present → trajectory unreadable
            // server-side (older run). Show the verdict, not an error.
            <span className="text-[10.5px] text-muted-foreground/60 pl-1">
              scorer detail unavailable for this run
            </span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

interface ThProps extends ThHTMLAttributes<HTMLTableCellElement> {
  numeric?: boolean;
  sticky?: boolean;
  active?: boolean;
  dir?: SortDir;
}

function Th({ numeric, sticky, active, dir, className, children, onClick, ...rest }: ThProps): JSX.Element {
  return (
    <th
      onClick={onClick}
      className={cn(
        "text-left text-[11px] font-medium text-muted-foreground bg-panel-2 px-3 py-2 border-b border-border",
        sticky && "sticky top-0",
        numeric && "text-right",
        onClick && "cursor-pointer hover:text-foreground",
        className,
      )}
      {...rest}
    >
      <div className={cn("inline-flex items-center gap-1.5", numeric && "justify-end w-full")}>
        {active && (
          <span className="text-accent text-[10px]">{dir === "desc" ? "↓" : "↑"}</span>
        )}
        {children}
      </div>
    </th>
  );
}

interface TdProps extends TdHTMLAttributes<HTMLTableCellElement> {
  numeric?: boolean;
}
function Td({ numeric, className, children, ...rest }: TdProps): JSX.Element {
  return (
    <td
      className={cn(
        "px-3 py-2 border-b border-border-soft",
        numeric && "text-right tnum",
        className,
      )}
      {...rest}
    >
      {children}
    </td>
  );
}
