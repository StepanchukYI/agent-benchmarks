from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ab_server.db import get_session
from ab_server.leaderboard import (
    CIGateStatus,
    LeaderboardMatrix,
    ParetoSeries,
    RegressionsPanel,
    TrendsOverview,
    TrendsSeries,
    compute_ci_gate,
    compute_matrix,
    compute_overview,
    compute_pareto,
    compute_regressions,
    compute_trends,
)

router = APIRouter(tags=["leaderboard"])


def _split_csv(values: list[str] | None) -> list[str] | None:
    if not values:
        return None
    out: list[str] = []
    for v in values:
        if v is None:
            continue
        for piece in str(v).split(","):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out or None


def _parse_iso(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail=f"Invalid ISO-8601 datetime: {value!r}"
        ) from exc


@router.get("/leaderboard", response_model=LeaderboardMatrix)
def get_leaderboard(
    session: Annotated[Session, Depends(get_session)],
    suites: Annotated[list[str] | None, Query()] = None,
    models: Annotated[list[str] | None, Query()] = None,
    tiers: Annotated[list[str] | None, Query()] = None,
    operator: str | None = None,
    trust: Annotated[list[str] | None, Query()] = None,
    date_from: str | None = None,
    date_to: str | None = None,
    dataset_versions: Annotated[list[str] | None, Query()] = None,
) -> LeaderboardMatrix:
    return compute_matrix(
        session,
        suites=_split_csv(suites),
        models=_split_csv(models),
        tiers=_split_csv(tiers),
        operator=operator,
        trust=_split_csv(trust),
        date_from=_parse_iso(date_from),
        date_to=_parse_iso(date_to),
        dataset_versions=_split_csv(dataset_versions),
    )


@router.get("/trends", response_model=TrendsSeries)
def get_trends(
    session: Annotated[Session, Depends(get_session)],
    model: str,
    suite: str,
    tier: str,
    days: int = 30,
) -> TrendsSeries:
    if days <= 0:
        raise HTTPException(status_code=400, detail="days must be > 0")
    return compute_trends(
        session, model=model, suite=suite, tier=tier, days=days
    )


@router.get("/leaderboard/pareto", response_model=ParetoSeries)
def get_pareto(
    session: Annotated[Session, Depends(get_session)],
    suites: Annotated[list[str] | None, Query()] = None,
    tiers: Annotated[list[str] | None, Query()] = None,
) -> ParetoSeries:
    return compute_pareto(
        session,
        suites=_split_csv(suites),
        tiers=_split_csv(tiers),
    )


@router.get("/trends/regressions", response_model=RegressionsPanel)
def get_trends_regressions(
    session: Annotated[Session, Depends(get_session)],
    window_days: int = 7,
    min_delta: float = 0.05,
    direction: str = "down",
    limit: int = 5,
) -> RegressionsPanel:
    if window_days <= 0:
        raise HTTPException(status_code=400, detail="window_days must be > 0")
    if direction not in ("up", "down"):
        raise HTTPException(
            status_code=400, detail="direction must be 'up' or 'down'"
        )
    if limit <= 0:
        raise HTTPException(status_code=400, detail="limit must be > 0")
    return compute_regressions(
        session,
        window_days=window_days,
        min_delta=min_delta,
        direction=direction,
        limit=limit,
    )


@router.get("/trends/overview", response_model=TrendsOverview)
def get_trends_overview(
    session: Annotated[Session, Depends(get_session)],
    window_days: int = 7,
) -> TrendsOverview:
    if window_days <= 0:
        raise HTTPException(status_code=400, detail="window_days must be > 0")
    return compute_overview(session, window_days=window_days)


@router.get("/trends/ci-gate", response_model=CIGateStatus)
def get_trends_ci_gate(
    session: Annotated[Session, Depends(get_session)],
) -> CIGateStatus:
    return compute_ci_gate(session)
