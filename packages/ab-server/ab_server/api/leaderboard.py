from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ab_server.db import get_session
from ab_server.leaderboard import (
    LeaderboardMatrix,
    ParetoSeries,
    TrendsSeries,
    compute_matrix,
    compute_pareto,
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
