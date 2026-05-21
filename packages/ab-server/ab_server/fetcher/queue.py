"""Background fetcher queue — durable, DB-backed, single-leader.

Public API:

* :func:`enqueue_repo_sync(session, repo_id, *, triggered_by="manual",
  max_attempts=None) -> FetchJob` — adds a row in status ``queued``. Idempotent
  by intent: if a non-terminal job already exists for the same repo, return
  it instead of stacking duplicates.
* :func:`claim_next_job(session) -> FetchJob | None` — atomically transitions
  the oldest queued (or retryable) job into ``in_progress``. Portable across
  SQLite + Postgres without ``SELECT ... FOR UPDATE``.
* :func:`process_job(session, job) -> FetchJob` — executes ``sync_repo`` for
  the job's repo and writes the outcome (status, attempts, error, result).
* :func:`run_one(session) -> FetchJob | None` — convenience wrapper:
  ``claim_next_job`` + ``process_job``. Returns ``None`` if no work.

Background poller:

A FastAPI lifespan task calls :func:`run_one` every
``Settings.fetch_queue_poll_interval_sec``. The poll loop owns its own DB
session lifecycle.

Concurrency:

The claim is implemented as ``UPDATE fetch_jobs SET status='in_progress'
WHERE id = (SELECT id FROM fetch_jobs WHERE status='queued' ORDER BY
enqueued_at LIMIT 1)``. Returning row counts tell us whether we won the race.
On SQLite the connection's WAL + the row lock gives us atomicity; on Postgres
the statement is fully serializable. For multi-instance deployments this
would need a per-row lease with a heartbeat — out of scope for the homelab
target, called out in the module docstring rather than silently broken.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import update
from sqlmodel import Session, select

from ab_server.models.fetch_job import FetchJob

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)

# Retry backoff: 1m, 5m, 15m. Caps total wait at ~21m before final fail.
_BACKOFF_SECONDS: tuple[int, ...] = (60, 300, 900)

# Non-terminal statuses — used by enqueue to detect duplicates.
_LIVE_STATUSES: frozenset[str] = frozenset({"queued", "in_progress", "retrying"})


def enqueue_repo_sync(
    session: Session,
    repo_id: UUID,
    *,
    triggered_by: str = "manual",
    max_attempts: int | None = None,
) -> FetchJob:
    """Add a queued job for ``repo_id``. Idempotent on live (non-terminal) jobs.

    If a job for the same repo is already queued / in_progress / retrying,
    return that job instead of stacking duplicates. Done/failed jobs do NOT
    block new enqueues — the sync may have new commits since.

    The default ``max_attempts`` mirrors :class:`FetchJob.max_attempts` (3).
    """
    existing = session.exec(
        select(FetchJob)
        .where(FetchJob.repo_id == repo_id)
        .where(FetchJob.status.in_(_LIVE_STATUSES))
        .order_by(FetchJob.enqueued_at.desc())
        .limit(1)
    ).first()
    if existing is not None:
        _log.info(
            "enqueue: returning existing live job %s (status=%s) for repo %s",
            existing.id,
            existing.status,
            repo_id,
        )
        return existing

    job = FetchJob(
        repo_id=repo_id,
        status="queued",
        triggered_by=triggered_by,
    )
    if max_attempts is not None:
        job.max_attempts = max(1, int(max_attempts))
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def claim_next_job(session: Session, *, now: datetime | None = None) -> FetchJob | None:
    """Atomically claim one queued/retryable job, return it (or None).

    Selection order:
        1. ``status='queued'`` rows by ``enqueued_at`` ascending (FIFO).
        2. ``status='retrying'`` rows whose ``next_attempt_after <= now``,
           by ``next_attempt_after`` ascending.

    Returns ``None`` when nothing is claimable right now (queue empty OR
    all retrying jobs are waiting out their backoff).
    """
    now = now or datetime.now(UTC)

    # Pick a candidate id without holding a long lock. The UPDATE below
    # is the atomic step — if a concurrent poller grabs the same id, the
    # UPDATE will affect 0 rows and we loop.
    for status, ts_col, ts_filter in (
        ("queued", FetchJob.enqueued_at, None),
        ("retrying", FetchJob.next_attempt_after, FetchJob.next_attempt_after <= now),
    ):
        stmt = select(FetchJob.id).where(FetchJob.status == status)
        if ts_filter is not None:
            stmt = stmt.where(ts_filter)
        stmt = stmt.order_by(ts_col.asc()).limit(1)
        candidate_id = session.exec(stmt).first()
        if candidate_id is None:
            continue

        # Atomic claim: refuse the update if another poller has already
        # moved the row out of the eligible status.
        result = session.exec(
            update(FetchJob)
            .where(FetchJob.id == candidate_id)
            .where(FetchJob.status == status)
            .values(
                status="in_progress",
                started_at=now,
            )
        )
        # SQLAlchemy 2.x exec_options; portable check on rowcount.
        rowcount = getattr(result, "rowcount", None)
        session.commit()
        if rowcount == 0:
            # Lost the race — try the next candidate (queued vs retrying).
            continue

        claimed = session.exec(
            select(FetchJob).where(FetchJob.id == candidate_id)
        ).first()
        return claimed

    return None


def _backoff_delay_for(attempt: int) -> timedelta:
    """Return the wait before the (attempt+1)-th attempt, after attempt failures."""
    idx = max(0, min(attempt - 1, len(_BACKOFF_SECONDS) - 1))
    return timedelta(seconds=_BACKOFF_SECONDS[idx])


def process_job(
    session: Session,
    job: FetchJob,
    *,
    now: datetime | None = None,
) -> FetchJob:
    """Run sync_repo for ``job.repo_id``, persist the outcome on the row.

    On success: status='done', result=SyncReport-as-dict.
    On failure with attempts remaining: status='retrying',
        next_attempt_after=now+backoff. Returns the row updated.
    On failure with attempts exhausted: status='failed'.

    The job MUST already be in ``in_progress`` (i.e. claimed). The poller
    handles the claim → process sequencing.
    """
    # Local imports keep the fetcher package importable without a full
    # server stack (handy for tests).
    from ab_server.fetcher.worker import sync_repo
    from ab_server.models.repo import RegisteredRepo as _Repo

    now = now or datetime.now(UTC)
    job.attempts += 1

    repo: _Repo | None = session.exec(
        select(_Repo).where(_Repo.id == job.repo_id)
    ).first()
    if repo is None:
        job.status = "failed"
        job.finished_at = now
        job.error = f"repo {job.repo_id} not found"
        session.add(job)
        session.commit()
        session.refresh(job)
        return job

    try:
        report = sync_repo(session, repo)
    except Exception as exc:
        job.error = f"{type(exc).__name__}: {exc}"
        _log.exception("fetch job %s raised", job.id)
        return _record_failure(session, job, now=now)

    job.result = {
        "repo_id": report.repo_id,
        "commit_sha": report.commit_sha,
        "inserted": report.inserted,
        "skipped": report.skipped,
        "rescored": report.rescored,
        "errors": list(report.errors),
    }
    if report.errors:
        # Soft errors: log them but still mark done so we don't retry
        # rescore-loop noise. clone_or_pull failures show up here too,
        # so check the first error category to decide.
        if any(err.startswith("clone_or_pull") for err in report.errors):
            job.error = report.errors[0]
            return _record_failure(session, job, now=now)
        job.error = "; ".join(report.errors[:3])

    job.status = "done"
    job.finished_at = now
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _record_failure(
    session: Session,
    job: FetchJob,
    *,
    now: datetime,
) -> FetchJob:
    if job.attempts < job.max_attempts:
        job.status = "retrying"
        job.next_attempt_after = now + _backoff_delay_for(job.attempts)
    else:
        job.status = "failed"
        job.finished_at = now
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def run_one(session: Session, *, now: datetime | None = None) -> FetchJob | None:
    """Claim + process one job. Returns the processed job, or None if idle."""
    claimed = claim_next_job(session, now=now)
    if claimed is None:
        return None
    return process_job(session, claimed, now=now)
