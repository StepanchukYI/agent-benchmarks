import { Download, Filter, MoreHorizontal } from "lucide-react";
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

export function LeaderboardMatrix(): JSX.Element {
  const [sort, setSort] = useState<Sort>({ key: 0, dir: "desc" });
  const { data: leaderboard } = useLeaderboard({});
  const { data: models } = useModels();
  const { data: trendsSeries } = useTrendsSeries("30d");

  const rows = leaderboard?.rows ?? [];
  const pillars = leaderboard?.pillars ?? PILLARS;
  const modelList: Model[] = models ?? [];
  const trends: Record<string, (number | null)[]> = trendsSeries?.per_model ?? {};

  const sorted = [...rows].sort((a, b) => {
    const sgn = sort.dir === "desc" ? -1 : 1;
    if (sort.key === -1) return sgn * a.model.localeCompare(b.model);
    return sgn * ((a.scores[sort.key] ?? 0) - (b.scores[sort.key] ?? 0));
  });

  function toggleSort(key: number): void {
    setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }));
  }

  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        title="Per-pillar scores"
        hint="7 models × 5 pillars · 5 operators"
        actions={
          <>
            <Button size="sm" variant="default"><Filter className="size-3" /> Columns</Button>
            <Button size="sm" variant="default"><Download className="size-3" /> Export CSV</Button>
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
              {pillars.map((p, i) => (
                <Th key={p} onClick={() => toggleSort(i)} active={sort.key === i} dir={sort.dir} numeric className="w-[120px]">
                  {p}
                </Th>
              ))}
              <Th className="w-[100px]" numeric>7d trend</Th>
              <Th className="w-[80px]" numeric>$/sweep</Th>
              <Th className="w-[32px]" />
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
                  {r.scores.map((s, idx) => (
                    <Td key={idx} numeric className="pr-4">
                      <span className="inline-flex items-center gap-0.5">
                        <ScoreCell score={s} delta={r.delta[idx]} />
                        {idx === 0 && <TrustDot tier={r.trust_tier} commit={r.source_commit_sha} size={10} />}
                      </span>
                    </Td>
                  ))}
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
                  <Td>
                    <Button variant="ghost" size="icon-sm"><MoreHorizontal className="size-3.5" /></Button>
                  </Td>
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
