from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ab_server.alerts.engine import evaluate_all
from ab_server.auth.dependency import get_current_user
from ab_server.db import get_session
from ab_server.models import AlertRule, User

router = APIRouter(tags=["alerts"])

_ALLOWED_DIRECTIONS = {"down", "up"}


class AlertChannel(BaseModel):
    type: str  # "email" | "webhook"
    target: str


class AlertCreate(BaseModel):
    name: str
    metric: str = "score_total"
    suite: str | None = None
    model: str | None = None
    tier: str | None = None
    direction: str = "down"
    threshold_pct: float = 5.0
    window_days: int = 7
    channels: list[AlertChannel] = Field(default_factory=list)
    enabled: bool = True


class AlertPatch(BaseModel):
    name: str | None = None
    metric: str | None = None
    suite: str | None = None
    model: str | None = None
    tier: str | None = None
    direction: str | None = None
    threshold_pct: float | None = None
    window_days: int | None = None
    channels: list[AlertChannel] | None = None
    enabled: bool | None = None


def _validate_direction(direction: str) -> None:
    if direction not in _ALLOWED_DIRECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"direction must be one of {sorted(_ALLOWED_DIRECTIONS)}",
        )


def _channels_to_storage(channels: list[AlertChannel] | None) -> list[dict[str, Any]]:
    if not channels:
        return []
    return [{"type": c.type, "target": c.target} for c in channels]


@router.post("/alerts", status_code=status.HTTP_201_CREATED)
def create_alert(
    payload: Annotated[AlertCreate, Body(...)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must be non-empty")
    _validate_direction(payload.direction)
    if payload.window_days <= 0:
        raise HTTPException(status_code=400, detail="window_days must be > 0")

    rule = AlertRule(
        user_id=user.id,
        name=payload.name,
        metric=payload.metric,
        suite=payload.suite,
        model=payload.model,
        tier=payload.tier,
        direction=payload.direction,
        threshold_pct=payload.threshold_pct,
        window_days=payload.window_days,
        channels=_channels_to_storage(payload.channels),
        enabled=payload.enabled,
    )
    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule.to_dict()


@router.get("/alerts")
def list_alerts(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(AlertRule).where(AlertRule.user_id == user.id).order_by(AlertRule.name)
    ).all()
    return [r.to_dict() for r in rows]


@router.patch("/alerts/{id}")
def patch_alert(
    id: str,
    payload: Annotated[AlertPatch, Body(...)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    rule = _load_alert(session, id, user)

    if payload.direction is not None:
        _validate_direction(payload.direction)
        rule.direction = payload.direction
    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="name must be non-empty")
        rule.name = payload.name
    if payload.metric is not None:
        rule.metric = payload.metric
    if payload.suite is not None:
        rule.suite = payload.suite
    if payload.model is not None:
        rule.model = payload.model
    if payload.tier is not None:
        rule.tier = payload.tier
    if payload.threshold_pct is not None:
        rule.threshold_pct = payload.threshold_pct
    if payload.window_days is not None:
        if payload.window_days <= 0:
            raise HTTPException(status_code=400, detail="window_days must be > 0")
        rule.window_days = payload.window_days
    if payload.channels is not None:
        rule.channels = _channels_to_storage(payload.channels)
    if payload.enabled is not None:
        rule.enabled = payload.enabled

    session.add(rule)
    session.commit()
    session.refresh(rule)
    return rule.to_dict()


@router.delete("/alerts/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert(
    id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    rule = _load_alert(session, id, user)
    session.delete(rule)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/alerts/evaluate")
def evaluate_alerts(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    rules = session.exec(
        select(AlertRule).where(AlertRule.user_id == user.id)
    ).all()
    result = evaluate_all(session, rules)
    return {
        "evaluated": result["evaluated"],
        "fired": [r.to_dict() for r in result["fired"]],
    }


def _load_alert(session: Session, id: str, user: User) -> AlertRule:
    try:
        aid = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from exc
    rule = session.get(AlertRule, aid)
    if rule is None or rule.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return rule
