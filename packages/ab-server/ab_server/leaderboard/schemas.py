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
    scores: list[float] = Field(default_factory=list)
    delta: list[float] = Field(default_factory=list)
    runs: int = 0
    variance: float = 0.0
    cost_per_task: float = 0.0
    latency_s: float = 0.0
    sweep_cost: float = 0.0
    dataset_pin: DatasetPin
    tier: str


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
    generated_at: datetime = Field(default_factory=_utcnow)


class TrendsSeriesResponse(BaseModel):
    per_model: dict[str, list[float]] = Field(default_factory=dict)
    per_operator: dict[str, list[float]] = Field(default_factory=dict)
    window_days: int = 0


class Operator(BaseModel):
    handle: str
    name: str
    initials: str
    color: str
    repo: str
    trust_default: str
    is_self: bool = False


class ModelInfo(BaseModel):
    id: str
    short: str
    vendor: str
    harness: str
    capabilities: list[str] = Field(default_factory=list)
    cost_per_1k_in: float = 0.0
    cost_per_1k_out: float = 0.0


class RegistryRepoOut(BaseModel):
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
    ci_gate_status: str
    ci_gate_blocked_merges_48h: int
    alerts_count_window: int
    alerts_actioned: int
    last_full_sweep_at: datetime | None = None
    last_full_sweep_cadence: str


class CIGateStatus(BaseModel):
    status: str
    blocked_merges_48h: int
    threshold_pct: float
    computed_at: datetime = Field(default_factory=_utcnow)
