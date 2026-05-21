import { useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { SubNav } from "../components/shell/SubNav";
import { PageHero } from "../components/shell/PageHero";
import { StatStrip, type Stat } from "../components/shell/StatStrip";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorBanner } from "../components/ui/ErrorBanner";
import { LoadingSkeleton } from "../components/ui/LoadingSkeleton";
import { FilterRail, type LeaderboardFilters } from "../components/leaderboard/FilterRail";
import { LeaderboardMatrix } from "../components/leaderboard/LeaderboardMatrix";
import { LeaderboardCards } from "../components/leaderboard/LeaderboardCards";
import { RightRail } from "../components/leaderboard/RightRail";
import { useTheme } from "../lib/theme";
import { useLeaderboard, useSuites } from "../api/hooks";
import { toState } from "../lib/ui-state";
import { deltaArrow } from "../lib/format";
import type { LeaderboardSummary } from "../lib/types";

type PillarFilter = "correctness" | "tool_skill" | "context_efficiency" | "latency_cost" | "memory_specific";

export default function Leaderboard(): JSX.Element {
  const { leaderboardView, setLeaderboardView } = useTheme();
  const suitesQuery = useSuites();
  const suiteList = suitesQuery.data ?? [];
  const [activePillar, setActivePillar] = useState<PillarFilter | null>(null);
  // Empty arrays = no constraint (show all). The sidebar toggles narrow
  // from there. Defaults must NOT pre-exclude rows — an earlier default of
  // operators:["evgeniy"] + trust:[official,verified] would have hidden
  // every self_reported StepanchukYI run.
  const [filters, setFilters] = useState<LeaderboardFilters>({
    suites: [],
    models: [],
    operators: [],
    trustTiers: [],
    datasetCurrentOnly: false,
    dateRange: "7d",
  });
  // Feed the sidebar filters into the query so toggling actually filters.
  // Omit empty arrays so "nothing selected" means "all", not "none".
  const leaderboardQuery = useLeaderboard({
    pillar: activePillar ?? undefined,
    suites: filters.suites.length ? filters.suites : undefined,
    models: filters.models.length ? filters.models : undefined,
    operators: filters.operators.length ? filters.operators : undefined,
    trust_tiers: filters.trustTiers.length ? filters.trustTiers : undefined,
    dataset_current_only: filters.datasetCurrentOnly || undefined,
    range: filters.dateRange === "24h" ? "24h" : filters.dateRange,
  });
  const leaderboardState = toState(leaderboardQuery, (r) => r.rows.length === 0);
  const summary = leaderboardQuery.data?.summary ?? null;
  const rows = leaderboardQuery.data?.rows ?? [];
  // Real trajectory total = sum of per-row run counts (NOT a hardcoded number).
  const trajectoryCount = rows.reduce((acc, r) => acc + (r.runs ?? 0), 0);
  const stats: Stat[] = buildLeaderboardStats(summary);

  return (
    <>
      <SubNav
        crumbs={[
          { label: "Leaderboard" },
          { label: "Default view", current: true },
        ]}
        tabs={[
          { id: "all", label: "All pillars", active: activePillar === null, onSelect: () => setActivePillar(null) },
          { id: "correctness", label: "Correctness", active: activePillar === "correctness", onSelect: () => setActivePillar("correctness") },
          { id: "memory", label: "Memory", active: activePillar === "memory_specific", onSelect: () => setActivePillar("memory_specific") },
          { id: "skill", label: "Skill router", active: activePillar === "tool_skill", onSelect: () => setActivePillar("tool_skill") },
          { id: "cost", label: "$ Efficiency", active: activePillar === "latency_cost", onSelect: () => setActivePillar("latency_cost") },
        ]}
      />

      <div className="flex flex-1 min-h-0">
        <FilterRail filters={filters} setFilters={setFilters} />

        <div className="flex-1 min-w-0 flex">
          <div className="flex-1 min-w-0 flex flex-col overflow-y-auto">
            <PageHero
              title="Leaderboard"
              subtitle={`${rows.length} ${rows.length === 1 ? "model" : "models"} · ${suiteList.length} suites · ${trajectoryCount.toLocaleString()} ${trajectoryCount === 1 ? "trajectory" : "trajectories"} scored`}
              actions={
                <>
                  <Button onClick={() => leaderboardQuery.refetch()}><RefreshCw className="size-3" /> Refresh</Button>
                  <div className="flex border border-border rounded-md overflow-hidden">
                    <Button
                      size="sm"
                      variant={leaderboardView === "matrix" ? "primary" : "ghost"}
                      className="rounded-none border-0"
                      onClick={() => setLeaderboardView("matrix")}
                    >
                      Matrix
                    </Button>
                    <Button
                      size="sm"
                      variant={leaderboardView === "cards" ? "primary" : "ghost"}
                      className="rounded-none border-0"
                      onClick={() => setLeaderboardView("cards")}
                    >
                      Cards
                    </Button>
                  </div>
                  <Button variant="primary"><Play className="size-3" fill="currentColor" /> New run</Button>
                </>
              }
            />

            <StatStrip stats={stats} />

            <div className="p-5 flex-1">
              {leaderboardState.kind === "loading" && (
                <LoadingSkeleton rows={6} columns={7} />
              )}
              {leaderboardState.kind === "error" && (
                <ErrorBanner
                  message={leaderboardState.message}
                  retry={() => leaderboardQuery.refetch()}
                />
              )}
              {leaderboardState.kind === "empty" && (
                <EmptyState
                  title="No verified runs yet."
                  hint={
                    <>
                      Run <span className="font-mono text-foreground-2">ab register</span> + {" "}
                      <span className="font-mono text-foreground-2">ab run --suite L0_smoke</span> to see scores here.
                    </>
                  }
                />
              )}
              {leaderboardState.kind === "ok" && (
                leaderboardView === "matrix" ? <LeaderboardMatrix /> : <LeaderboardCards />
              )}
            </div>
          </div>

          <RightRail />
        </div>
      </div>
    </>
  );
}

/**
 * Build the StatStrip rows from the server `summary` block. Falls back to
 * `—` placeholders when summary is null (no runs in window). Deltas use the
 * shared `deltaArrow` helper so colour tone (`deltaValue`) and arrow stay
 * in sync; null deltas render as blank with neutral tone.
 *
 * Correctness values from the server are 0..1; we render as % with one
 * decimal. Cost efficiency is USD (model spend / mean correctness).
 */
function buildLeaderboardStats(summary: LeaderboardSummary | null): Stat[] {
  if (!summary) {
    return [
      { label: "Mean correctness", value: "—", unit: "%", deltaValue: null },
      { label: "Runs in window", value: "—", deltaValue: null },
      { label: "Best correctness", value: "—", deltaValue: null },
      { label: "Best $/correctness", value: "—", deltaValue: null },
    ];
  }

  const meanCorrDelta = summary.mean_correctness_delta;
  const runsDelta = summary.runs_count_delta;
  const bestCorrDelta = summary.best_correctness_delta;
  const bestCostDelta = summary.best_cost_efficiency_delta;

  return [
    {
      label: "Mean correctness",
      value: (summary.mean_correctness * 100).toFixed(1),
      unit: "%",
      delta:
        meanCorrDelta == null
          ? undefined
          : `${deltaArrow(meanCorrDelta)} ${(meanCorrDelta * 100).toFixed(1)} vs prev 7d`,
      deltaValue: meanCorrDelta,
    },
    {
      label: "Runs in window",
      value: summary.runs_count_window.toLocaleString(),
      delta:
        runsDelta == null ? undefined : `${deltaArrow(runsDelta)} ${runsDelta}`,
      deltaValue: runsDelta,
    },
    {
      label: "Best correctness",
      value: summary.best_correctness_model ?? "—",
      unit:
        summary.best_correctness_value == null
          ? undefined
          : (summary.best_correctness_value * 100).toFixed(1),
      delta:
        bestCorrDelta == null
          ? undefined
          : `${deltaArrow(bestCorrDelta)} ${(bestCorrDelta * 100).toFixed(1)}`,
      deltaValue: bestCorrDelta,
    },
    {
      label: "Best $/correctness",
      value: summary.best_cost_efficiency_model ?? "—",
      unit:
        summary.best_cost_efficiency_value_usd == null
          ? undefined
          : `$${summary.best_cost_efficiency_value_usd.toFixed(2)}`,
      delta:
        bestCostDelta == null
          ? undefined
          : `${deltaArrow(bestCostDelta)} ${bestCostDelta.toFixed(2)}`,
      deltaValue: bestCostDelta,
    },
  ];
}
