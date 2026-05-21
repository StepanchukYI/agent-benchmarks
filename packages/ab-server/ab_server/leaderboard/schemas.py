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


class LeaderboardRow(BaseModel):
    model: str
    tier: str
    cells: dict[str, LeaderboardCell] = Field(default_factory=dict)
    row_mean: float = 0.0


class LeaderboardMatrix(BaseModel):
    rows: list[LeaderboardRow] = Field(default_factory=list)
    suites: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
    filters_applied: dict[str, Any] = Field(default_factory=dict)


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
