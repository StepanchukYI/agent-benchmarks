from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from ab_harness.scorers.privacy_check import privacy_check_scorer
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from ab_server.api._trajectory_view import (
    assemble_trajectory_view,
    resolve_submission_paths,
)
from ab_server.config import Settings
from ab_server.db import get_session
from ab_server.models import (
    RegisteredRepo,
    ScorerVerdictRow,
    Submission,
    TaskResult,
    User,
)

router = APIRouter(tags=["submissions"])


def _serialize_submission(
    submission: Submission,
    task_result: TaskResult | None = None,
) -> dict[str, Any]:
    return {
        "id": str(submission.id),
        "registered_repo_id": str(submission.registered_repo_id),
        "source_commit_sha": submission.source_commit_sha,
        "source_path": submission.source_path,
        "trust_tier": submission.trust_tier,
        "model": submission.model,
        "tier": submission.tier,
        "dataset_version": submission.dataset_version,
        "discrepancy_pct": submission.discrepancy_pct,
        "ingested_at": submission.ingested_at.isoformat(),
        "re_scored_at": submission.re_scored_at.isoformat() if submission.re_scored_at else None,
        "suite": task_result.suite if task_result else None,
        "task_id": task_result.task_id if task_result else None,
        "score_total": task_result.score_total if task_result else None,
    }


def _serialize_task_result(task_result: TaskResult) -> dict[str, Any]:
    return {
        "id": str(task_result.id),
        "task_id": task_result.task_id,
        "suite": task_result.suite,
        "model": task_result.model,
        "tier": task_result.tier,
        "status": task_result.status,
        "score_total": task_result.score_total,
        "cost_usd": task_result.cost_usd,
        "latency_ms": task_result.latency_ms,
    }


def _serialize_verdict(row: ScorerVerdictRow) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "scorer_name": row.scorer_name,
        "kind": row.kind,
        "pass": row.pass_,
        "score": row.score,
        "detail": row.detail,
    }


@router.get("/submissions")
def list_submissions(
    session: Annotated[Session, Depends(get_session)],
    operator: str | None = Query(default=None),
    suite: str | None = Query(default=None),
    tier: str | None = Query(default=None),
    trust: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    # Always join RegisteredRepo so we can enforce is_public on every row.
    # Private repo submissions must only surface via owner-scoped endpoints,
    # which this is not. Pre-fix this filter only fired when ?operator= was
    # set, leaking private rows on the unfiltered list view.
    stmt = (
        select(Submission, TaskResult)
        .join(
            TaskResult,
            TaskResult.submission_id == Submission.id,
            isouter=True,
        )
        .join(RegisteredRepo, RegisteredRepo.id == Submission.registered_repo_id)
        .where(RegisteredRepo.is_public == True)  # noqa: E712 — SQL bool
    )
    if tier:
        stmt = stmt.where(Submission.tier == tier)
    if trust:
        stmt = stmt.where(Submission.trust_tier == trust)
    if since:
        stmt = stmt.where(Submission.ingested_at >= since)
    if suite:
        stmt = stmt.where(TaskResult.suite == suite)
    if operator:
        stmt = stmt.join(User, User.id == RegisteredRepo.user_id).where(
            User.handle == operator
        )

    stmt = stmt.order_by(Submission.ingested_at.desc()).offset(offset).limit(limit)
    rows = session.exec(stmt).all()
    items = [_serialize_submission(sub, tr) for sub, tr in rows]
    return {"items": items, "limit": limit, "offset": offset, "count": len(items)}


@router.get("/submissions/{id}")
def get_submission(
    id: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    try:
        sub_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from exc
    submission = session.get(Submission, sub_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    task_result = session.exec(
        select(TaskResult).where(TaskResult.submission_id == submission.id)
    ).first()
    verdicts: list[dict[str, Any]] = []
    if task_result:
        verdict_rows = session.exec(
            select(ScorerVerdictRow).where(ScorerVerdictRow.task_result_id == task_result.id)
        ).all()
        verdicts = [_serialize_verdict(v) for v in verdict_rows]

    return {
        "submission": _serialize_submission(submission, task_result),
        "task_result": _serialize_task_result(task_result) if task_result else None,
        "verdicts": verdicts,
    }


def _resolve_submission(session: Session, id: str) -> Submission:
    try:
        sub_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from exc
    submission = session.get(Submission, sub_id)
    if submission is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return submission


@router.get("/submissions/{id}/trajectory")
def get_submission_trajectory(
    id: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    submission = _resolve_submission(session, id)
    settings = Settings()
    traj_path, repo, task_result = resolve_submission_paths(
        session, submission, settings.fetcher_cache_dir
    )
    if not traj_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"trajectory file missing at {traj_path}",
        )
    return assemble_trajectory_view(
        traj_path,
        submission=submission,
        task_result=task_result,
        repo=repo,
    )


@router.get("/submissions/{id}/privacy-scan")
def get_submission_privacy_scan(
    id: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    submission = _resolve_submission(session, id)
    settings = Settings()
    traj_path, _repo, _tr = resolve_submission_paths(
        session, submission, settings.fetcher_cache_dir
    )
    if not traj_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"trajectory file missing at {traj_path}",
        )
    verdict = privacy_check_scorer(
        workdir=None,
        task=None,
        trajectory_path=Path(traj_path),
        mode="replay",
    )
    detail = verdict.detail if isinstance(verdict.detail, dict) else {}
    hits = detail.get("hits", []) if isinstance(detail.get("hits"), list) else []
    total_hits = int(detail.get("total_hits", 0) or 0)
    high_hits = int(detail.get("high_severity_hits", 0) or 0)
    return {
        "ok": bool(verdict.pass_),
        "total_hits": total_hits,
        "high_severity_hits": high_hits,
        "hits": hits,
    }
