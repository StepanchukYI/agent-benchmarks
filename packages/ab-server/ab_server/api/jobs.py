"""Background fetch-job inspection.

* ``GET /jobs/{id}`` — single job by id (404 if not found).
* ``GET /jobs`` — list, optionally filtered by status / repo / triggered_by.
* ``POST /jobs/{id}/retry`` — manually re-queue a failed/done job (operator
  tool; rate-limited but no other gate).

All endpoints require an authenticated user; jobs are scoped to repos the
user owns. Admins (future flag) can see everything; for now there is no
admin role so cross-user visibility is blocked.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from ab_server.auth.dependency import get_current_user
from ab_server.db import get_session
from ab_server.fetcher.queue import enqueue_repo_sync
from ab_server.models import FetchJob, RegisteredRepo, User

router = APIRouter(tags=["jobs"])


def _user_owns(session: Session, user: User, repo_id: UUID) -> bool:
    repo = session.exec(
        select(RegisteredRepo).where(RegisteredRepo.id == repo_id)
    ).first()
    return repo is not None and repo.user_id == user.id


def _load_job(session: Session, id: str) -> FetchJob:
    try:
        job_uuid = UUID(id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid job id",
        ) from exc
    job = session.exec(select(FetchJob).where(FetchJob.id == job_uuid)).first()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job not found",
        )
    return job


@router.get("/jobs/{id}")
def get_job(
    id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    job = _load_job(session, id)
    if not _user_owns(session, user, job.repo_id):
        # 404 not 403 to avoid leaking existence of jobs the caller can't see.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job not found",
        )
    return job.to_dict()


@router.get("/jobs")
def list_jobs(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    status_: str | None = Query(default=None, alias="status"),
    repo_id: str | None = Query(default=None),
    triggered_by: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    # Scope to the caller's repos. Build the repo-id set once, then filter.
    owned_repo_ids = [
        r.id
        for r in session.exec(
            select(RegisteredRepo).where(RegisteredRepo.user_id == user.id)
        ).all()
    ]
    if not owned_repo_ids:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    stmt = select(FetchJob).where(FetchJob.repo_id.in_(owned_repo_ids))
    if status_:
        stmt = stmt.where(FetchJob.status == status_)
    if repo_id:
        try:
            stmt = stmt.where(FetchJob.repo_id == UUID(repo_id))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid repo_id",
            ) from exc
    if triggered_by:
        stmt = stmt.where(FetchJob.triggered_by == triggered_by)

    # Count + window in two queries — same pattern as runs.list_runs.
    from sqlalchemy import func

    total = session.exec(
        select(func.count()).select_from(stmt.subquery())
    ).one()
    rows = session.exec(
        stmt.order_by(FetchJob.enqueued_at.desc()).offset(offset).limit(limit)
    ).all()
    return {
        "items": [j.to_dict() for j in rows],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


@router.post("/jobs/{id}/retry", status_code=202)
def retry_job(
    id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Re-enqueue a fetch for the same repo as the given (terminal) job.

    Allowed states: `done`, `failed`. Re-queueing a live job (queued /
    in_progress / retrying) is rejected with 409 — there is already a
    job in flight for that repo.
    """
    job = _load_job(session, id)
    if not _user_owns(session, user, job.repo_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="job not found",
        )
    if job.status not in {"done", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"cannot retry job in status={job.status!r}; already live",
        )
    new_job = enqueue_repo_sync(
        session,
        job.repo_id,
        triggered_by=f"retry:{user.handle}",
    )
    return {
        "previous_job_id": str(job.id),
        "job_id": str(new_job.id),
        "job_status": new_job.status,
        "enqueued_at": new_job.enqueued_at.isoformat()
        if new_job.enqueued_at
        else datetime.now(UTC).isoformat(),
    }
