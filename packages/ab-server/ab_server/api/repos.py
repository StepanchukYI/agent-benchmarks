from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session, select

from ab_server.auth.dependency import get_current_user
from ab_server.config import Settings
from ab_server.db import get_session
from ab_server.fetcher.queue import enqueue_repo_sync
from ab_server.fetcher.worker import sync_repo
from ab_server.models import RegisteredRepo, User

router = APIRouter(tags=["repos"])


class _RepoCreate(BaseModel):
    repo_url: str
    default_branch: str = "main"
    is_public: bool = True


def _serialize(repo: RegisteredRepo) -> dict[str, Any]:
    return {
        "id": str(repo.id),
        "user_id": str(repo.user_id),
        "repo_url": repo.repo_url,
        "default_branch": repo.default_branch,
        "is_public": repo.is_public,
        "status": repo.status,
        "last_synced_at": repo.last_synced_at.isoformat() if repo.last_synced_at else None,
        "sync_cursor": repo.sync_cursor,
        "created_at": repo.created_at.isoformat(),
    }


@router.post("/repos", status_code=status.HTTP_201_CREATED)
def register_repo(
    payload: Annotated[_RepoCreate, Body(...)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    existing = session.exec(
        select(RegisteredRepo)
        .where(RegisteredRepo.user_id == user.id)
        .where(RegisteredRepo.repo_url == payload.repo_url)
    ).first()
    if existing is not None:
        if existing.status == "archived":
            existing.status = "registered"
            existing.default_branch = payload.default_branch
            existing.is_public = payload.is_public
            session.add(existing)
            session.commit()
            session.refresh(existing)
        return _serialize(existing)

    repo = RegisteredRepo(
        user_id=user.id,
        repo_url=payload.repo_url,
        default_branch=payload.default_branch,
        is_public=payload.is_public,
        status="registered",
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return _serialize(repo)


@router.get("/repos")
def list_repos(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(RegisteredRepo)
        .where(RegisteredRepo.user_id == user.id)
        .where(RegisteredRepo.status != "archived")
    ).all()
    return [_serialize(r) for r in rows]


@router.delete("/repos/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_repo(
    id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    repo = _load_repo(session, id, user)
    repo.status = "archived"
    session.add(repo)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/repos/{id}/sync")
def trigger_sync(
    id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    response: Response,
    inline: bool = False,
) -> dict[str, Any]:
    """Enqueue a fetch job; return 202 + job_id (or 200 + result if inline).

    Default (recommended): the request returns 202 immediately with a job_id.
    Poll ``GET /jobs/{job_id}`` to observe progress. The background fetcher
    poller drains the queue on its own schedule
    (``Settings.fetch_queue_poll_interval_sec``).

    Pass ``?inline=true`` to run synchronously inside the request handler
    and return 200 + the full SyncReport. Useful for one-off ops where you
    want the result immediately, but blocks a gunicorn worker for the
    duration. Same underlying ``sync_repo`` is invoked in both paths.
    """
    repo = _load_repo(session, id, user)
    started_at = datetime.now(UTC)
    if inline:
        report = sync_repo(session, repo)
        response.status_code = status.HTTP_200_OK
        return {
            "sync_id": str(repo.id),
            "mode": "inline",
            "started_at": started_at.isoformat(),
            "commit_sha": report.commit_sha,
            "inserted": report.inserted,
            "skipped": report.skipped,
            "rescored": report.rescored,
            "errors": report.errors,
        }
    job = enqueue_repo_sync(session, repo.id, triggered_by=f"user:{user.handle}")
    settings = Settings()
    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "sync_id": str(repo.id),
        "mode": "queued",
        "job_id": str(job.id),
        "job_status": job.status,
        "enqueued_at": job.enqueued_at.isoformat(),
        "next_poll_in_sec": settings.fetch_queue_poll_interval_sec,
    }


def _load_repo(session: Session, id: str, user: User) -> RegisteredRepo:
    try:
        repo_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from exc
    repo = session.get(RegisteredRepo, repo_id)
    if repo is None or repo.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return repo
