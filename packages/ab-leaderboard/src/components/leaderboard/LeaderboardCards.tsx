import { Sparkline } from "../ui/Sparkline";
import { MiniBar } from "../ui/MiniBar";
import { OperatorTag } from "../domain/OperatorTag";
import { StaleDatasetPill } from "../domain/StaleDatasetPill";
import { TrustDot } from "../domain/TrustDot";
import { PILLARS } from "../../lib/mock-data";
import { useLeaderboard, useModels, useTrendsSeries } from "../../api/hooks";
import { deltaArrow, deltaTone, fmtMoney, fmtScore } from "../../lib/format";
import { cn } from "../../lib/utils";

const VENDOR_HEX: Record<string, string> = {
  anthropic: "#d97757",
  openai: "#10a37f",
  google: "#4285f4",
  zhipu: "#8b5cf6",
  minimax: "#f59e0b",
};

/** PILLARS index of the Context pillar — shows real token usage, not a score. */
const CONTEXT_PILLAR_IDX = 1;

/** Native title= tooltip explaining what each pillar label measures. */
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

export function LeaderboardCards(): JSX.Element {
  const { data: leaderboard } = useLeaderboard({});
  const { data: models } = useModels();
  const { data: trendsSeries } = useTrendsSeries("30d");
  const rows = leaderboard?.rows ?? [];
  const pillars = leaderboard?.pillars ?? PILLARS;
  const modelList = models ?? [];
  const trends: Record<string, (number | null)[]> = trendsSeries?.per_model ?? {};

  return (
    <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))" }}>
      {rows.map((r, i) => {
        const m = modelList.find((x) => x.id === r.model);
        if (!m) return null;
        const color = VENDOR_HEX[m.vendor]!;
        // null = pillar had no runs (excluded from the headline mean); 0 = real score (kept).
        const present = r.scores.filter((s): s is number => s != null);
        const overall = present.length ? present.reduce((a, b) => a + b, 0) / present.length : 0;
        return (
          <div key={r.model} className="rounded-lg border border-border bg-panel p-4 flex flex-col gap-3.5">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2.5">
                <span
                  className="grid place-items-center size-[22px] rounded-md font-bold text-[11px]"
                  style={{ background: color + "22", color }}
                >
                  #{i + 1}
                </span>
                <div>
                  <div className="font-mono text-[13px] font-semibold flex items-center gap-1.5">
                    {m.id}
                    <TrustDot tier={r.trust_tier} commit={r.source_commit_sha} size={10} />
                  </div>
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 mt-0.5">
                    <OperatorTag handle={r.operator} avatarSize={13} />
                    <span>·</span>
                    <span>{r.runs} runs</span>
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div className="text-[22px] font-semibold tnum tracking-tight">{overall.toFixed(1)}</div>
                <div className="text-[10.5px] text-muted-foreground">overall</div>
                <div className="text-[13px] font-semibold tnum mt-1 text-foreground-2">
                  {r.pass_rate == null ? "—" : `${r.pass_rate.toFixed(1)}%`}
                </div>
                <div className="text-[10.5px] text-muted-foreground">passed</div>
                <div className="mt-1">
                  <StaleDatasetPill pin={r.dataset_pin} />
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              {pillars.map((p, idx) => {
                if (idx === CONTEXT_PILLAR_IDX) {
                  // Context pillar shows ACTUAL median tokens/task, not the
                  // synthetic 0..100 efficiency score (product-owner ask).
                  const n = r.pillar_counts[idx] ?? 0;
                  return (
                    <div key={p} className="grid items-center gap-2.5" style={{ gridTemplateColumns: "90px 1fr 64px" }}>
                      <span className="text-muted-foreground text-[11px]" title={PILLAR_TOOLTIP[p]}>{p}</span>
                      <span className="text-muted-foreground text-[11px]">tokens / task</span>
                      <span className="text-[11.5px] tnum flex justify-end items-baseline gap-1 font-semibold">
                        {fmtTokens(r.tokens_total)}
                        {n > 0 && <span className="text-[10px] text-muted-foreground/60 font-normal">n={n}</span>}
                      </span>
                    </div>
                  );
                }
                const s = r.scores[idx] ?? null;
                if (s == null) {
                  // No runs for this pillar — show an honest em-dash, no bar/delta.
                  return (
                    <div key={p} className="grid items-center gap-2.5" style={{ gridTemplateColumns: "90px 1fr 64px" }}>
                      <span className="text-muted-foreground text-[11px]" title={PILLAR_TOOLTIP[p]}>{p}</span>
                      <span className="text-muted-foreground text-[11px]">no data</span>
                      <span className="text-[11.5px] tnum flex justify-end text-muted-foreground">{fmtScore(s)}</span>
                    </div>
                  );
                }
                const n = r.pillar_counts[idx] ?? 0;
                const d = r.delta[idx] ?? 0;
                const tone = deltaTone(d);
                return (
                  <div key={p} className="grid items-center gap-2.5" style={{ gridTemplateColumns: "90px 1fr 64px" }}>
                    <span className="text-muted-foreground text-[11px]" title={PILLAR_TOOLTIP[p]}>{p}</span>
                    <MiniBar value={s} tone={s > 80 ? "pass" : s > 65 ? "neutral" : "warn"} width="100%" />
                    <span className="text-[11.5px] tnum flex justify-end items-baseline gap-1">
                      <span className="font-semibold">{fmtScore(s)}</span>
                      <span
                        className={cn(
                          "text-[10px]",
                          tone === "up" && "text-pass",
                          tone === "dn" && "text-fail",
                          tone === "flat" && "text-muted-foreground",
                        )}
                      >
                        {deltaArrow(d)}{Math.abs(d).toFixed(1)}
                      </span>
                      {n > 0 && <span className="text-[10px] text-muted-foreground/60">n={n}</span>}
                    </span>
                  </div>
                );
              })}
            </div>

            <div className="flex items-center justify-between border-t border-border-soft pt-3">
              <div className="flex gap-3.5 text-[11px]">
                <div>
                  <span className="text-muted-foreground">cost</span>
                  <span className="font-mono ml-1">{fmtMoney(r.sweep_cost)}</span>
                </div>
                <div>
                  <span className="text-muted-foreground">p50</span>
                  <span className="font-mono ml-1">{r.latency_s.toFixed(1)}s</span>
                </div>
              </div>
              <Sparkline data={(trends[r.model] ?? []).filter((v): v is number => v != null)} width={84} height={18} color={color} fill />
            </div>
          </div>
        );
      })}
    </div>
  );
}
