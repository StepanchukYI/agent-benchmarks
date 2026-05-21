import { useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { SubNav } from "../components/shell/SubNav";
import { PageHero } from "../components/shell/PageHero";
import { StatStrip, type Stat } from "../components/shell/StatStrip";
import { Pill } from "../components/ui/Pill";
import { Button } from "../components/ui/Button";
import { FilterRail, type LeaderboardFilters } from "../components/leaderboard/FilterRail";
import { LeaderboardMatrix } from "../components/leaderboard/LeaderboardMatrix";
import { LeaderboardCards } from "../components/leaderboard/LeaderboardCards";
import { RightRail } from "../components/leaderboard/RightRail";
import { useTheme } from "../lib/theme";
import { useLeaderboard, useModels, useSuites } from "../api/hooks";

export default function Leaderboard(): JSX.Element {
  const { leaderboardView, setLeaderboardView } = useTheme();
  const { data: models } = useModels();
  const { data: suites } = useSuites();
  const { data: leaderboard } = useLeaderboard({});
  const modelList = models ?? [];
  const suiteList = suites ?? [];
  const rows = leaderboard?.rows ?? [];
  const [filters, setFilters] = useState<LeaderboardFilters>({
    suites: ["L0_smoke", "L1_memory_write", "L1_retrieval", "L2_mcp"],
    models: modelList.map((m) => m.id),
    operators: ["evgeniy"],
    trustTiers: ["official", "verified"],
    datasetCurrentOnly: true,
    dateRange: "7d",
  });
  const meanC = rows.length > 0 ? rows.reduce((acc, r) => acc + (r.scores[0] ?? 0), 0) / rows.length : 0;
  const totalRuns = rows.reduce((acc, r) => acc + r.runs, 0);
  const totalCost = rows.reduce((acc, r) => acc + r.sweep_cost * r.runs * 0.1, 0);

  const stats: Stat[] = [
    { label: "Mean correctness", value: meanC.toFixed(1), unit: "/100", delta: "▲ 1.4 vs prev 7d", deltaValue: 1.4 },
    { label: "Runs in window", value: totalRuns.toLocaleString(), delta: "▲ 312", deltaValue: 1 },
    { label: "Total cost", value: "$" + totalCost.toFixed(2), delta: "▼ 4.10", deltaValue: -4.1 },
    { label: "Best correctness", value: "claude-opus-4-1", unit: "89.4", delta: "▲ 1.2", deltaValue: 1.2 },
    { label: "Best $/correctness", value: "minimax-m2", unit: "$0.11", delta: "· stable", deltaValue: 0 },
  ];

  return (
    <>
      <SubNav
        crumbs={[
          { label: "Leaderboard" },
          { label: "Default view", current: true },
        ]}
        tabs={[
          { id: "all", label: "All pillars", active: true },
          { id: "correctness", label: "Correctness" },
          { id: "memory", label: "Memory" },
          { id: "skill", label: "Skill router" },
          { id: "cost", label: "$ Efficiency" },
        ]}
        trailing={<span className="text-muted-foreground text-[11px]">Updated 4m ago</span>}
      />

      <div className="flex flex-1 min-h-0">
        <FilterRail filters={filters} setFilters={setFilters} />

        <div className="flex-1 min-w-0 flex">
          <div className="flex-1 min-w-0 flex flex-col overflow-y-auto">
            <PageHero
              title="Leaderboard"
              subtitle={`${modelList.length} models · ${suiteList.length} suites · last 7 days · 2 759 trajectories scored`}
              actions={
                <>
                  <Pill tone="idle" size="sm">Last refresh 4m ago</Pill>
                  <Button><RefreshCw className="size-3" /> Refresh</Button>
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
              {leaderboardView === "matrix" ? <LeaderboardMatrix /> : <LeaderboardCards />}
            </div>
          </div>

          <RightRail />
        </div>
      </div>
    </>
  );
}
