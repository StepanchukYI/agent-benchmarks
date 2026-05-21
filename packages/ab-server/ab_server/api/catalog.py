from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from ab_server.db import get_session
from ab_server.leaderboard import ModelInfo, Operator
from ab_server.models import RegisteredRepo, Submission, TaskResult, User

router = APIRouter(tags=["catalog"])


def _color_from_handle(handle: str) -> str:
    h = hashlib.sha256(handle.encode("utf-8")).hexdigest()
    return "#" + h[:6]


def _initials(handle: str) -> str:
    name = handle.strip()
    if not name:
        return "??"
    return name[:2].upper()


@router.get("/operators", response_model=list[Operator])
def list_operators(
    session: Annotated[Session, Depends(get_session)],
) -> list[Operator]:
    stmt = (
        select(
            User.handle,
            RegisteredRepo.repo_url,
            Submission.trust_tier,
            Submission.id,
        )
        .select_from(Submission)
        .join(RegisteredRepo, RegisteredRepo.id == Submission.registered_repo_id)
        .join(User, User.id == RegisteredRepo.user_id)
    )

    handles_seen: dict[str, dict] = {}
    for handle, repo_url, trust_tier, _sub_id in session.exec(stmt).all():
        if not handle:
            continue
        entry = handles_seen.setdefault(
            handle,
            {"repos": [], "trusts": []},
        )
        if repo_url and repo_url not in entry["repos"]:
            entry["repos"].append(repo_url)
        if trust_tier:
            entry["trusts"].append(trust_tier)

    operators: list[Operator] = [
        Operator(
            handle="self",
            name="self",
            initials="SE",
            color="#888888",
            repo="",
            trust_default="self_reported",
            is_self=True,
        )
    ]

    for handle, info in sorted(handles_seen.items()):
        trusts = info["trusts"]
        counts: dict[str, int] = {}
        for t in trusts:
            counts[t] = counts.get(t, 0) + 1
        trust_default = (
            max(counts.items(), key=lambda kv: kv[1])[0] if counts else "self_reported"
        )
        operators.append(
            Operator(
                handle=handle,
                name=handle,
                initials=_initials(handle),
                color=_color_from_handle(handle),
                repo=info["repos"][0] if info["repos"] else "",
                trust_default=trust_default,
                is_self=False,
            )
        )

    return operators


def _models_catalog_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "models_catalog.yaml"


def _load_models_catalog() -> dict[str, dict]:
    path = _models_catalog_path()
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    out: dict[str, dict] = {}
    for entry in data.get("models", []):
        if isinstance(entry, dict) and "id" in entry:
            out[entry["id"]] = entry
    return out


def _model_from_catalog(entry: dict) -> ModelInfo:
    return ModelInfo(
        id=entry["id"],
        short=entry.get("short", entry["id"]),
        vendor=entry.get("vendor", "unknown"),
        harness=entry.get("harness", "unknown"),
        capabilities=list(entry.get("capabilities", []) or []),
        cost_per_1k_in=float(entry.get("cost_per_1k_in", 0.0)),
        cost_per_1k_out=float(entry.get("cost_per_1k_out", 0.0)),
    )


@router.get("/models", response_model=list[ModelInfo])
def list_models(
    session: Annotated[Session, Depends(get_session)],
) -> list[ModelInfo]:
    catalog = _load_models_catalog()

    seen_models: set[str] = set()
    for row in session.exec(
        select(TaskResult.model, func.count(TaskResult.id)).group_by(TaskResult.model)
    ).all():
        model_name, _n = row
        if model_name:
            seen_models.add(model_name)

    out: list[ModelInfo] = []
    emitted: set[str] = set()
    for model_id, entry in catalog.items():
        out.append(_model_from_catalog(entry))
        emitted.add(model_id)
    for model_id in sorted(seen_models - emitted):
        out.append(
            ModelInfo(
                id=model_id,
                short=model_id,
                vendor="unknown",
                harness="unknown",
                capabilities=[],
                cost_per_1k_in=0.0,
                cost_per_1k_out=0.0,
            )
        )
    return out
