from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ab_server.db import get_session
from ab_server.leaderboard import (
    CIGateStatus,
    HeatmapResponse,
    LeaderboardResponse,
    ParetoHistorySeries,
    ParetoSeries,
    RegressionsPanel,
    TrendsOverview,
    TrendsSeries,
    TrendsSeriesResponse,
    compute_ci_gate,
    compute_heatmap,
    compute_leaderboard_response,
    compute_overview,
    compute_pareto,
    compute_pareto_history,
    compute_regressions,
    compute_trends,
    compute_trends_series,
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


_RANGE_TO_DAYS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}


_PillarLiteral = Literal[
    "correctness",
    "tool_skill",
    "context_efficiency",
    "latency_cost",
    "memory_specific",
]


@router.get("/leaderboard", response_model=LeaderboardResponse)
def get_leaderboard(
    session: Annotated[Session, Depends(get_session)],
    suites: Annotated[list[str] | None, Query()] = None,
    models: Annotated[list[str] | None, Query()] = None,
    tiers: Annotated[list[str] | None, Query()] = None,
    operators: Annotated[list[str] | None, Query()] = None,
    trust_tiers: Annotated[list[str] | None, Query()] = None,
    dataset_current_only: bool = False,
    range: Annotated[str | None, Query()] = None,
    date_from: str | None = None,
    date_to: str | None = None,
    dataset_versions: Annotated[list[str] | None, Query()] = None,
    include_task_tags: Annotated[list[str] | None, Query()] = None,
    exclude_task_tags: Annotated[list[str] | None, Query()] = None,
    pillar: Annotated[_PillarLiteral | None, Query()] = None,
) -> LeaderboardResponse:
    range_days: int | None = None
    if range is not None:
        if range not in _RANGE_TO_DAYS:
            raise HTTPException(
                status_code=400,
                detail=f"range must be one of {list(_RANGE_TO_DAYS)}",
            )
        range_days = _RANGE_TO_DAYS[range]

    return compute_leaderboard_response(
        session,
        suites=_split_csv(suites),
        models=_split_csv(models),
        tiers=_split_csv(tiers),
        operators=_split_csv(operators),
        trust=_split_csv(trust_tiers),
        date_from=_parse_iso(date_from),
        date_to=_parse_iso(date_to),
        dataset_versions=_split_csv(dataset_versions),
        range_days=range_days,
        include_task_tags=_split_csv(include_task_tags),
        exclude_task_tags=_split_csv(exclude_task_tags),
        pillar=pillar,
    )


@router.get("/tags")
def get_known_tags() -> dict[str, list[str]]:
    """All sensitivity tags declared on any known task.

    Drives the FE's tag-filter picker. Cached after first call;
    rebuild via process restart or by hitting a future
    /admin/refresh-tags endpoint.
    """
    from ab_server.leaderboard.task_tags import all_known_tags

    return {"tags": sorted(all_known_tags())}


@router.get("/trends", response_model=TrendsSeries)
def get_trends(
    session: Annotated[Session, Depends(get_session)],
    model: str | None = None,
    suite: str | None = None,
    tier: str | None = None,
    days: int = 30,
) -> TrendsSeries:
    if days <= 0:
        raise HTTPException(status_code=400, detail="days must be > 0")
    if not model or not suite or not tier:
        raise HTTPException(
            status_code=400,
            detail="model, suite, and tier query params are required",
        )
    return compute_trends(
        session, model=model, suite=suite, tier=tier, days=days
    )


@router.get("/trends/series", response_model=TrendsSeriesResponse)
def get_trends_series(
    session: Annotated[Session, Depends(get_session)],
    range: Literal["7d", "30d", "90d"] = "30d",
    show_operators: bool = False,
) -> TrendsSeriesResponse:
    days = {"7d": 7, "30d": 30, "90d": 90}[range]
    return compute_trends_series(
        session, window_days=days, show_operators=show_operators
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


@router.get("/leaderboard/heatmap", response_model=HeatmapResponse)
def get_heatmap(
    session: Annotated[Session, Depends(get_session)],
    suites: Annotated[list[str] | None, Query()] = None,
    models: Annotated[list[str] | None, Query()] = None,
    tiers: Annotated[list[str] | None, Query()] = None,
) -> HeatmapResponse:
    return compute_heatmap(
        session,
        suites=_split_csv(suites),
        models=_split_csv(models),
        tiers=_split_csv(tiers),
    )


@router.get("/leaderboard/pareto/history", response_model=ParetoHistorySeries)
def get_pareto_history(
    session: Annotated[Session, Depends(get_session)],
    window: Literal["7d", "30d", "90d"] = "30d",
    suites: Annotated[list[str] | None, Query()] = None,
    tiers: Annotated[list[str] | None, Query()] = None,
) -> ParetoHistorySeries:
    days = {"7d": 7, "30d": 30, "90d": 90}[window]
    return compute_pareto_history(
        session,
        window_days=days,
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
