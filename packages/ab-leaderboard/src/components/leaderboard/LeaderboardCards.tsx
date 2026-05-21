import { Sparkline } from "../ui/Sparkline";
import { MiniBar } from "../ui/MiniBar";
import { OperatorTag } from "../domain/OperatorTag";
import { StaleDatasetPill } from "../domain/StaleDatasetPill";
import { TrustDot } from "../domain/TrustDot";
import { LEADERBOARD, MODELS, PILLARS, TRENDS } from "../../lib/mock-data";
import { deltaArrow, deltaTone, fmtMoney } from "../../lib/format";
import { cn } from "../../lib/utils";

const VENDOR_HEX: Record<string, string> = {
  anthropic: "#d97757",
  openai: "#10a37f",
  google: "#4285f4",
  zhipu: "#8b5cf6",
  minimax: "#f59e0b",
};

export function LeaderboardCards(): JSX.Element {
  return (
    <div className="grid gap-3.5" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(330px, 1fr))" }}>
      {LEADERBOARD.map((r, i) => {
        const m = MODELS.find((x) => x.id === r.model)!;
        const color = VENDOR_HEX[m.vendor]!;
        const overall = r.scores.reduce((a, b) => a + b, 0) / r.scores.length;
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
                <div className="mt-1.5">
                  <StaleDatasetPill pin={r.dataset_pin} />
                </div>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              {PILLARS.map((p, idx) => {
                const s = r.scores[idx]!;
                const d = r.delta[idx] ?? 0;
                const tone = deltaTone(d);
                return (
                  <div key={p} className="grid items-center gap-2.5" style={{ gridTemplateColumns: "90px 1fr 64px" }}>
                    <span className="text-muted-foreground text-[11px]">{p}</span>
                    <MiniBar value={s} tone={s > 80 ? "pass" : s > 65 ? "neutral" : "warn"} width="100%" />
                    <span className="text-[11.5px] tnum flex justify-end items-baseline gap-1">
                      <span className="font-semibold">{s.toFixed(1)}</span>
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
              <Sparkline data={TRENDS[r.model]!} width={84} height={18} color={color} fill />
            </div>
          </div>
        );
      })}
    </div>
  );
}
