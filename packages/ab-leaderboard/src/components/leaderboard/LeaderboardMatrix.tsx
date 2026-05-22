import { Check, Download, Filter } from "lucide-react";
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
import { PILLARS } from "../../lib/mock-data";
import { useLeaderboard, useModels, useTrendsSeries } from "../../api/hooks";
import { fmtMoney } from "../../lib/format";
import { cn } from "../../lib/utils";
import type { Model } from "../../lib/types";

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

/** Median tokens/task as "12,400 tok"; "—" when unmeasured (0). */
function fmtTokens(n: number | null | undefined): string {
  if (n == null || n === 0) return "—";
  return `${n.toLocaleString("en-US")} tok`;
}

export function LeaderboardMatrix(): JSX.Element {
  const [sort, setSort] = useState<Sort>({ key: 0, dir: "desc" });
  const [hiddenPillars, setHiddenPillars] = useState<Set<number>>(new Set());
  const [columnsOpen, setColumnsOpen] = useState(false);
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
    const header = ["model", "operator", ...pillars, "sweep_cost_usd"];
    const escape = (v: string): string =>
      /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
    const lines = sorted
      .filter((r) => modelList.some((m) => m.id === r.model))
      .map((r) =>
        [
          r.model,
          r.operator,
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
              <Th onClick={() => toggleSort(-1)} active={sort.key === -1} dir={sort.dir} sticky className="pl-4 w-[280px]">
                Model
              </Th>
              <Th className="w-[170px]">Operator</Th>
              {pillars.map((p, i) =>
                hiddenPillars.has(i) ? null : (
                  <Th key={p} onClick={() => toggleSort(i)} active={sort.key === i} dir={sort.dir} numeric className="w-[120px]">
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
              return (
                <tr key={r.model} className="hover:bg-panel-2/50">
                  <Td className="pl-4">
                    <div className="flex items-center gap-2.5">
                      <span className="w-[18px] text-muted-foreground text-[11px] tnum">{i + 1}</span>
                      <ModelCell model={m} />
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
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
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
