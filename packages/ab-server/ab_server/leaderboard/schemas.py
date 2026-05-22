from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class LeaderboardCell(BaseModel):
    score_mean: float
    n: int
    latest_run_at: datetime | None = None
    trust_tiers: list[str] = Field(default_factory=list)
    cost_usd_mean: float = 0.0
    score_correctness: float | None = None
    score_context_eff: float | None = None
    score_tool_skill: float | None = None
    score_memory: float | None = None
    score_latency: float | None = None
    sparkline_7d: list[float] = Field(default_factory=list)
    previous_mean: float | None = None
    delta: float | None = None


class LeaderboardMatrixRow(BaseModel):
    model: str
    tier: str
    cells: dict[str, LeaderboardCell] = Field(default_factory=dict)
    row_mean: float = 0.0


class LeaderboardMatrix(BaseModel):
    rows: list[LeaderboardMatrixRow] = Field(default_factory=list)
    suites: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
    filters_applied: dict[str, Any] = Field(default_factory=dict)


class DatasetPin(BaseModel):
    version: str
    behind: int


class LeaderboardRow(BaseModel):
    model: str
    operator: str
    trust_tier: str
    source_commit_sha: str
    # Per-pillar scores (0..100), aligned to the pillar order. An entry is null
    # when no run measured that pillar for this row — the FE skips nulls in the
    # overall mean rather than averaging in a phantom 0.
    scores: list[float | None] = Field(default_factory=list)
    delta: list[float | None] = Field(default_factory=list)
    runs: int = 0
    variance: float = 0.0
    cost_per_task: float = 0.0
    latency_s: float = 0.0
    tokens_total: int = 0
    turns_total: int = 0
    sweep_cost: float = 0.0
    dataset_pin: DatasetPin
    tier: str
    # pass_rate = 100 * (passed==True count) / (passed is not None count)
    # null when denominator is 0 (no task had a decided scorer)
    pass_rate: float | None = None
    # Per-pillar sample sizes, index-aligned to `scores`. Each value is the
    # count of task-results that contributed a non-null score to that pillar.
    pillar_counts: list[int] = Field(default_factory=list)
    # harness/effort from the run_start trajectory event; null for pre-B1 rows.
    harness: str | None = None
    effort: str | None = None


class LeaderboardSummary(BaseModel):
    mean_correctness: float
    mean_correctness_delta: float | None = None
    runs_count_window: int
    runs_count_delta: int | None = None
    best_correctness_model: str | None = None
    best_correctness_value: float | None = None
    best_correctness_delta: float | None = None
    best_cost_efficiency_model: str | None = None
    best_cost_efficiency_value_usd: float | None = None
    best_cost_efficiency_delta: float | None = None
    # Mean of per-row pass_rates (only rows with pass_rate != None contribute).
    # null when no row in the window has any decided scorer.
    mean_pass_rate: float | None = None


class LeaderboardResponse(BaseModel):
    rows: list[LeaderboardRow] = Field(default_factory=list)
    pillars: list[str] = Field(
        default_factory=lambda: [
            "Correctness",
            "Context",
            "Tool/Skill",
            "Memory",
            "Latency $",
        ]
    )
    summary: LeaderboardSummary | None = None
    generated_at: datetime = Field(default_factory=_utcnow)


class TrendsSeriesResponse(BaseModel):
    # None entries = days with no runs (gaps), not zero scores.
    per_model: dict[str, list[float | None]] = Field(default_factory=dict)
    per_operator: dict[str, list[float | None]] = Field(default_factory=dict)
    window_days: int = 0


class Operator(BaseModel):
    handle: str
    name: str
    initials: str
    color: str
    repo: str
    trust_default: str
    is_self: bool = False


class SuiteOut(BaseModel):
    id: str
    layer: str
    name: str
    description: str
    task_count: int


class ModelInfo(BaseModel):
    id: str
    short: str
    vendor: str
    harness: str
    capabilities: list[str] = Field(default_factory=list)
    cost_per_1k_in: float = 0.0
    cost_per_1k_out: float = 0.0


class RegistryRepoOut(BaseModel):
    id: str
    repo: str
    owner: str
    branch: str
    runs: int
    last_synced: str
    status: str
    error: str | None = None


class ScrubberRule(BaseModel):
    name: str
    pattern: str
    replacement: str


class TrendsPoint(BaseModel):
    date: str
    score_mean: float
    n: int


class TrendsSeries(BaseModel):
    model: str
    suite: str
    tier: str
    points: list[TrendsPoint] = Field(default_factory=list)


class ParetoPoint(BaseModel):
    model: str
    tier: str
    cost_usd_mean: float
    score_mean: float
    n: int
    on_frontier: bool = False


class ParetoSeries(BaseModel):
    points: list[ParetoPoint] = Field(default_factory=list)


class HeatmapCell(BaseModel):
    score_correctness: float | None = None
    n: int = 0


class HeatmapRow(BaseModel):
    model: str
    tier: str
    cells: dict[str, HeatmapCell] = Field(default_factory=dict)


class HeatmapResponse(BaseModel):
    rows: list[HeatmapRow] = Field(default_factory=list)
    suites: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)


class ParetoHistoryPoint(BaseModel):
    at: datetime
    cost_usd_mean: float
    score_mean: float
    n: int


class ParetoHistorySeriesItem(BaseModel):
    model: str
    tier: str
    history: list[ParetoHistoryPoint] = Field(default_factory=list)


class ParetoHistorySeries(BaseModel):
    series: list[ParetoHistorySeriesItem] = Field(default_factory=list)
    window_days: int = 0
    generated_at: datetime = Field(default_factory=_utcnow)


class RegressionItem(BaseModel):
    model: str
    tier: str
    suite: str
    score_now: float
    score_prev: float
    delta_pct: float
    n_now: int
    n_prev: int
    last_run_at: datetime | None = None
    operator_handle: str | None = None


class RegressionsPanel(BaseModel):
    direction: str
    window_days: int
    items: list[RegressionItem] = Field(default_factory=list)


class TrendsOverview(BaseModel):
    window_days: int
    active_regressions_count: int
    improvements_count: int
    active_regressions_delta_30d: int | None = None
    improvements_delta_30d: int | None = None
    ci_gate_status: str
    ci_gate_blocked_merges_48h: int
    alerts_count_window: int
    alerts_actioned: int | None = None
    last_full_sweep_at: datetime | None = None
    last_full_sweep_cadence: str | None = None


class CIGateStatus(BaseModel):
    status: str
    blocked_merges_48h: int
    threshold_pct: float
    computed_at: datetime = Field(default_factory=_utcnow)


class RowTaskScorerItem(BaseModel):
    name: str
    pass_: bool | None = Field(default=None, alias="pass")
    score: float | None = None
    detail: str | dict | None = None

    model_config = {"populate_by_name": True}


class RowTaskItem(BaseModel):
    task_id: str
    suite: str
    passed: bool | None = None
    scorers: list[RowTaskScorerItem] = Field(default_factory=list)
