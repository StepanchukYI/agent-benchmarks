from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ab_server.auth.dependency import get_current_user
from ab_server.db import get_session
from ab_server.models import RunPreset, User

router = APIRouter(tags=["presets"])


class PresetCreate(BaseModel):
    name: str
    suites: list[str] = Field(default_factory=list)
    task_ids: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    tier: str = "T0"
    repetitions: int = 1
    sandbox: str = "local"
    concurrency: int = 1


@router.post("/presets", status_code=status.HTTP_201_CREATED)
def create_preset(
    payload: Annotated[PresetCreate, Body(...)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must be non-empty")

    existing = session.exec(
        select(RunPreset)
        .where(RunPreset.user_id == user.id)
        .where(RunPreset.name == payload.name)
    ).first()
    if existing is not None:
        existing.suites = payload.suites
        existing.task_ids = payload.task_ids
        existing.models = payload.models
        existing.tier = payload.tier
        existing.repetitions = payload.repetitions
        existing.sandbox = payload.sandbox
        existing.concurrency = payload.concurrency
        existing.updated_at = datetime.now(UTC)
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing.to_dict()

    preset = RunPreset(
        user_id=user.id,
        name=payload.name,
        suites=payload.suites,
        task_ids=payload.task_ids,
        models=payload.models,
        tier=payload.tier,
        repetitions=payload.repetitions,
        sandbox=payload.sandbox,
        concurrency=payload.concurrency,
    )
    session.add(preset)
    session.commit()
    session.refresh(preset)
    return preset.to_dict()


@router.get("/presets")
def list_presets(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(RunPreset).where(RunPreset.user_id == user.id).order_by(RunPreset.name)
    ).all()
    return [r.to_dict() for r in rows]


@router.delete("/presets/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preset(
    id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    preset = _load_preset(session, id, user)
    session.delete(preset)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _load_preset(session: Session, id: str, user: User) -> RunPreset:
    try:
        pid = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from exc
    preset = session.get(RunPreset, pid)
    if preset is None or preset.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return preset
