from __future__ import annotations

import asyncio
import json
import statistics
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import Session, select

from ab_server.api._trajectory_view import (
    assemble_trajectory_view,
    resolve_submission_paths,
)
from ab_server.auth.dependency import get_current_user
from ab_server.config import Settings
from ab_server.db import get_session
from ab_server.models import Run, Submission, TaskResult, User

router = APIRouter(tags=["runs"])

# Poll interval for the SSE endpoint. Tests override this module-level constant
# to keep streaming assertions fast.
SSE_POLL_INTERVAL_SECONDS: float = 2.0
SSE_MAX_DURATION_SECONDS: float = 30 * 60  # 30 minutes cap

# Fallbacks used when we have no historical data for a task in the lookback
# window.
ESTIMATE_FALLBACK_COST_USD = 0.05
ESTIMATE_FALLBACK_DURATION_SEC = 120.0
ESTIMATE_LOOKBACK_DAYS = 30

_TERMINAL_STATUSES = {"completed", "error", "timeout"}
_VALID_STATUSES = {"scheduled", "in_progress", "completed", "error", "timeout"}


class RunCreate(BaseModel):
    suites: list[str] = Field(default_factory=list)
    task_ids: list[str] | None = None
    models: list[str]
    tier: str
    dataset_version: str | None = None
    repetitions: int = 1
    sandbox: str = "local"
    concurrency: int = 1
    label: str | None = None
    # v1 ships ZERO server-side dispatch. To create a Run row, the caller
    # MUST acknowledge they will run the benchmark locally via `ab run` and
    # publish results via `ab publish`. Setting this to False (or omitting)
    # makes POST /runs return 422 with the CLI command to copy.
    dispatch_via_cli: bool = False


def _build_cli_command(payload: RunCreate, model: str) -> str:
    parts: list[str] = ["ab run", f"--model {model}", f"--tier {payload.tier}"]
    if payload.suites:
        parts.append(f"--suite {payload.suites[0]}")
    if payload.task_ids:
        for tid in payload.task_ids:
            parts.append(f"--task {tid}")
    if payload.repetitions > 1:
        parts.append(f"--repetitions {payload.repetitions}")
    if payload.dataset_version:
        parts.append(f"--dataset-version {payload.dataset_version}")
    return " ".join(parts)


def _serialize_summary(run: Run, *, finished_count: int | None = None) -> dict[str, Any]:
    progress_pct: float | None = None
    if run.expected_total is not None and run.expected_total > 0 and finished_count is not None:
        progress_pct = round(min(1.0, finished_count / run.expected_total) * 100.0, 2)
    return {
        "id": str(run.id),
        "label": run.label,
        "suite": run.suite,
        "model": run.model,
        "tier": run.tier,
        "tier_hash": run.tier_hash,
        "dataset_version": run.dataset_version,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "cost_total_usd": run.cost_total_usd,
        "expected_total": run.expected_total,
        "progress_pct": progress_pct,
    }


def _serialize_task_result(tr: TaskResult) -> dict[str, Any]:
    return {
        "id": str(tr.id),
        "task_id": tr.task_id,
        "suite": tr.suite,
        "model": tr.model,
        "tier": tr.tier,
        "status": tr.status,
        "score_total": tr.score_total,
        "cost_usd": tr.cost_usd,
        "latency_ms": tr.latency_ms,
    }


def _count_finished(session: Session, run_id: UUID) -> int:
    stmt = select(TaskResult).where(TaskResult.run_id == run_id)
    rows = session.exec(stmt).all()
    return sum(1 for r in rows if r.status in _TERMINAL_STATUSES)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
def create_run(
    payload: Annotated[RunCreate, Body(...)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Any:
    """Record a planned run.

    v1 does NOT execute runs server-side — operators run benchmarks locally
    via `ab run` and publish via `ab publish` (ADR-007). The UI's "Launch run"
    button maps to "Copy CLI command" backed by this endpoint:

    - When `dispatch_via_cli=false` (default): respond 422 with the CLI command
      the operator should copy + reasoning. No DB write.
    - When `dispatch_via_cli=true`: record one `Run` row per model with
      `status="scheduled"` so the UI can display the planned run, and echo back
      `cli_commands` so the operator can copy + paste into their shell.
    """
    if not payload.models:
        raise HTTPException(status_code=400, detail="models must be non-empty")
    if payload.repetitions <= 0:
        raise HTTPException(status_code=400, detail="repetitions must be > 0")

    cli_commands = [_build_cli_command(payload, m) for m in payload.models]

    if not payload.dispatch_via_cli:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "server_side_dispatch_not_implemented",
                "message": (
                    "v1 does not execute runs server-side. Copy the CLI commands "
                    "below into your shell, then `ab publish` to see results "
                    "in the leaderboard. Re-POST with `dispatch_via_cli=true` to "
                    "record the planned run in your dashboard."
                ),
                "cli_commands": cli_commands,
            },
        )

    primary_suite = payload.suites[0] if payload.suites else ""
    n_tasks = len(payload.task_ids) if payload.task_ids else 0
    expected_total_per_model = (n_tasks or 0) * payload.repetitions

    run_ids: list[str] = []
    for model in payload.models:
        run = Run(
            tenant_id=str(user.id),
            suite=primary_suite,
            model=model,
            tier=payload.tier,
            tier_hash="",
            dataset_version=payload.dataset_version or "",
            status="scheduled",
            label=payload.label,
            expected_total=expected_total_per_model if expected_total_per_model > 0 else None,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_ids.append(str(run.id))

    return {
        "run_ids": run_ids,
        "label": payload.label,
        "cli_commands": cli_commands,
        "note": "Server does not execute runs; copy cli_commands locally then `ab publish`.",
    }


@router.get("/runs")
def list_runs(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    if status_filter is not None and status_filter not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(_VALID_STATUSES)}",
        )
    base = select(Run).where(Run.tenant_id == str(user.id))
    count_stmt = select(func.count()).select_from(Run).where(Run.tenant_id == str(user.id))
    if status_filter is not None:
        base = base.where(Run.status == status_filter)
        count_stmt = count_stmt.where(Run.status == status_filter)

    # Push pagination into SQL so we don't materialize the entire user's
    # run history per request (H8). Total is a separate COUNT query under
    # the same filters.
    page_stmt = base.order_by(Run.started_at.desc()).offset(offset).limit(limit)
    page = session.exec(page_stmt).all()
    total = int(session.exec(count_stmt).one() or 0)
    items = [
        _serialize_summary(r, finished_count=_count_finished(session, r.id)) for r in page
    ]
    return {"items": items, "limit": limit, "offset": offset, "total": total}


@router.post("/runs/estimate")
def estimate_run(
    payload: Annotated[RunCreate, Body(...)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    if not payload.models:
        raise HTTPException(status_code=400, detail="models must be non-empty")

    task_ids = list(payload.task_ids or [])
    n_models = len(payload.models)
    repetitions = max(1, payload.repetitions)
    concurrency = max(1, payload.concurrency)

    expected_trajectories = max(1, len(task_ids)) * n_models * repetitions

    cutoff = datetime.now(UTC) - timedelta(days=ESTIMATE_LOOKBACK_DAYS)
    sample_sizes: list[int] = []

    total_cost = 0.0
    total_latency_sec = 0.0

    iter_tasks = task_ids if task_ids else [None]
    for task_id in iter_tasks:
        stmt = (
            select(TaskResult.cost_usd, TaskResult.latency_ms)
            .join(Run, Run.id == TaskResult.run_id, isouter=True)
            .where(TaskResult.tier == payload.tier)
            .where((Run.started_at.is_(None)) | (Run.started_at >= cutoff))
        )
        if task_id is not None:
            stmt = stmt.where(TaskResult.task_id == task_id)
        rows = session.exec(stmt).all()
        costs = [float(c or 0.0) for c, _ in rows]
        latencies_ms = [int(l_ms or 0) for _, l_ms in rows]
        sample_sizes.append(len(rows))

        median_cost = (
            statistics.median(costs) if costs else ESTIMATE_FALLBACK_COST_USD
        )
        if latencies_ms:
            median_latency_sec = statistics.median(latencies_ms) / 1000.0
        else:
            median_latency_sec = ESTIMATE_FALLBACK_DURATION_SEC

        total_cost += median_cost
        total_latency_sec += median_latency_sec

    estimated_cost_usd = total_cost * repetitions * n_models
    avg_latency_sec_per_task = total_latency_sec / max(1, len(iter_tasks))
    estimated_duration_min = (
        expected_trajectories * avg_latency_sec_per_task
        / concurrency
        / 60.0
    )

    avg_sample_size = (
        int(sum(sample_sizes) / len(sample_sizes)) if sample_sizes else 0
    )
    return {
        "estimated_cost_usd": round(estimated_cost_usd, 4),
        "estimated_duration_min": round(estimated_duration_min, 2),
        "expected_trajectories": expected_trajectories,
        "basis": {
            "window_days": ESTIMATE_LOOKBACK_DAYS,
            "sample_size_per_task": avg_sample_size,
        },
    }


@router.get("/runs/{id}")
def get_run(
    id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    run = _load_run(session, id, user)
    finished = _count_finished(session, run.id)
    summary = _serialize_summary(run, finished_count=finished)
    task_rows = session.exec(select(TaskResult).where(TaskResult.run_id == run.id)).all()
    summary["task_results"] = [_serialize_task_result(t) for t in task_rows]
    return summary


def _make_session_factory(request: Request):
    """Build a session factory that honors test dependency overrides.

    Tests override `get_session` to point at a temp SQLite file. The SSE
    generator can't call the dependency directly (no DI machinery once the
    response is returned), so we capture the override (or the default) at
    request time and reuse it on each poll tick.

    Resolves overrides via ``request.app.dependency_overrides`` — this is
    the SAME app instance FastAPI used to inject ``get_session`` into the
    enclosing endpoint, so tests that create a fresh ``create_app()`` are
    honored. The prior implementation imported ``ab_server.main.app`` at
    call time, which captured the module-level singleton even when the
    test had built its own app via the factory.
    """
    override = request.app.dependency_overrides.get(get_session)
    if override is not None:
        def _factory() -> Session:
            gen = override()
            return next(gen)
        return _factory

    from ab_server.db import get_engine

    def _default() -> Session:
        return Session(get_engine())

    return _default


async def _stream_progress(
    run_id: UUID,
    started_at: datetime,
    session_factory,
) -> Any:
    """SSE generator: yields a `progress` event every poll tick.

    Stops on terminal status or after SSE_MAX_DURATION_SECONDS.
    """
    while True:
        terminal = False
        session = session_factory()
        try:
            run = session.get(Run, run_id)
            if run is None:
                yield 'data: {"status": "not_found"}\n\n'
                return
            finished = _count_finished(session, run_id)
            total = run.expected_total or 0
            current_task: str | None = None
            rows = session.exec(
                select(TaskResult).where(TaskResult.run_id == run_id)
            ).all()
            in_progress = [t for t in rows if t.status not in _TERMINAL_STATUSES]
            if in_progress:
                current_task = in_progress[0].task_id
            payload = {
                "finished": finished,
                "total": total,
                "current_task_id": current_task,
                "status": run.status,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            terminal = run.status in _TERMINAL_STATUSES
        finally:
            session.close()

        if terminal:
            return

        if (datetime.now(UTC) - started_at).total_seconds() >= SSE_MAX_DURATION_SECONDS:
            yield 'data: {"status": "timeout_streaming"}\n\n'
            return

        await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)


@router.get("/runs/{id}/stream")
def stream_run(
    id: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> StreamingResponse:
    run = _load_run(session, id, user)
    factory = _make_session_factory(request)
    return StreamingResponse(
        _stream_progress(run.id, datetime.now(UTC), factory),
        media_type="text/event-stream",
    )


def _parse_uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return None


def _find_submission_for_run(
    session: Session, run_or_submission_id: str, task_id: str
) -> Submission | None:
    parsed = _parse_uuid(run_or_submission_id)
    if parsed is None:
        return None

    # First try: submission_id == path id (sibling addressing).
    submission = session.get(Submission, parsed)
    if submission is not None:
        result = session.exec(
            select(TaskResult)
            .where(TaskResult.submission_id == submission.id)
            .where(TaskResult.task_id == task_id)
        ).first()
        if result is not None:
            return submission

    # Second try: run_id matches a TaskResult.run_id with the given task.
    result = session.exec(
        select(TaskResult)
        .where(TaskResult.run_id == parsed)
        .where(TaskResult.task_id == task_id)
    ).first()
    if result is not None and result.submission_id is not None:
        sub = session.get(Submission, result.submission_id)
        if sub is not None:
            return sub
    return None


@router.get("/runs/{id}/trajectories/{task_id}")
def get_trajectory(
    id: str,
    task_id: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    submission = _find_submission_for_run(session, id, task_id)
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="trajectory not found"
        )
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


def _load_run(session: Session, id: str, user: User) -> Run:
    try:
        run_id = UUID(id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found") from exc
    run = session.get(Run, run_id)
    if run is None or run.tenant_id != str(user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return run
