"""Background fetch queue — enqueue / claim / process semantics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from ab_server.fetcher.queue import (
    _BACKOFF_SECONDS,
    claim_next_job,
    enqueue_repo_sync,
    process_job,
    run_one,
)
from ab_server.models import FetchJob, RegisteredRepo, User
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    engine = create_engine(
        f"sqlite:///{tmp_path/'fetch.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_repo(session: Session, *, handle: str = "alice") -> RegisteredRepo:
    user = User(github_id=f"gh-{handle}", handle=handle, avatar_url=None)
    session.add(user)
    session.commit()
    session.refresh(user)
    repo = RegisteredRepo(
        user_id=user.id,
        repo_url=f"https://github.com/{handle}/results",
        default_branch="main",
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


def test_enqueue_creates_queued_job(session: Session) -> None:
    repo = _seed_repo(session)
    job = enqueue_repo_sync(session, repo.id, triggered_by="manual")
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.triggered_by == "manual"
    assert job.repo_id == repo.id


def test_enqueue_is_idempotent_for_live_jobs(session: Session) -> None:
    repo = _seed_repo(session)
    first = enqueue_repo_sync(session, repo.id)
    second = enqueue_repo_sync(session, repo.id)
    assert first.id == second.id, "stacking duplicate live jobs"
    # Confirm we have exactly one row.
    rows = session.exec(select(FetchJob).where(FetchJob.repo_id == repo.id)).all()
    assert len(rows) == 1


def test_enqueue_allows_new_after_done(session: Session) -> None:
    repo = _seed_repo(session)
    first = enqueue_repo_sync(session, repo.id)
    first.status = "done"
    first.finished_at = datetime.now(UTC)
    session.add(first)
    session.commit()
    second = enqueue_repo_sync(session, repo.id)
    assert second.id != first.id
    assert second.status == "queued"


def test_claim_returns_oldest_queued(session: Session) -> None:
    repo = _seed_repo(session)
    now = datetime.now(UTC)
    # Insert two queued jobs with explicit different timestamps; bypass
    # the idempotency check by manually creating rows.
    older = FetchJob(repo_id=repo.id, status="queued", enqueued_at=now - timedelta(minutes=5))
    newer = FetchJob(repo_id=repo.id, status="queued", enqueued_at=now)
    session.add(older)
    session.add(newer)
    session.commit()
    session.refresh(older)
    session.refresh(newer)

    claimed = claim_next_job(session)
    assert claimed is not None
    assert claimed.id == older.id
    assert claimed.status == "in_progress"
    assert claimed.started_at is not None


def test_claim_returns_none_when_empty(session: Session) -> None:
    assert claim_next_job(session) is None


def test_claim_picks_up_retrying_when_due(session: Session) -> None:
    repo = _seed_repo(session)
    now = datetime.now(UTC)
    # One retrying job whose backoff is in the past — should be claimed.
    job = FetchJob(
        repo_id=repo.id,
        status="retrying",
        attempts=1,
        next_attempt_after=now - timedelta(seconds=1),
    )
    session.add(job)
    session.commit()

    claimed = claim_next_job(session, now=now)
    assert claimed is not None
    assert claimed.status == "in_progress"


def test_claim_skips_retrying_when_not_due(session: Session) -> None:
    repo = _seed_repo(session)
    now = datetime.now(UTC)
    job = FetchJob(
        repo_id=repo.id,
        status="retrying",
        attempts=1,
        next_attempt_after=now + timedelta(minutes=10),
    )
    session.add(job)
    session.commit()

    assert claim_next_job(session, now=now) is None


def test_process_success_marks_done(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _seed_repo(session)
    job = enqueue_repo_sync(session, repo.id)
    job.status = "in_progress"  # simulate prior claim
    session.add(job)
    session.commit()

    # Stub sync_repo so we don't hit network/git.
    def fake_sync(_session: Session, _repo: RegisteredRepo) -> Any:
        from ab_server.fetcher.worker import SyncReport

        return SyncReport(
            repo_id=str(_repo.id),
            commit_sha="abc123",
            inserted=2,
            skipped=1,
            rescored=2,
            errors=[],
        )

    monkeypatch.setattr("ab_server.fetcher.worker.sync_repo", fake_sync)

    result = process_job(session, job)
    assert result.status == "done"
    assert result.attempts == 1
    assert result.finished_at is not None
    assert result.result == {
        "repo_id": str(repo.id),
        "commit_sha": "abc123",
        "inserted": 2,
        "skipped": 1,
        "rescored": 2,
        "errors": [],
    }


def test_process_clone_failure_retries(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _seed_repo(session)
    job = enqueue_repo_sync(session, repo.id)
    job.status = "in_progress"
    session.add(job)
    session.commit()

    def fake_sync(_session: Session, _repo: RegisteredRepo) -> Any:
        from ab_server.fetcher.worker import SyncReport

        return SyncReport(
            repo_id=str(_repo.id),
            commit_sha=None,
            inserted=0,
            skipped=0,
            rescored=0,
            errors=["clone_or_pull failed: boom"],
        )

    monkeypatch.setattr("ab_server.fetcher.worker.sync_repo", fake_sync)

    result = process_job(session, job)
    assert result.status == "retrying"
    assert result.attempts == 1
    assert result.next_attempt_after is not None
    expected_delta = timedelta(seconds=_BACKOFF_SECONDS[0])
    elapsed = result.next_attempt_after - datetime.now(UTC).replace(tzinfo=result.next_attempt_after.tzinfo)
    # The schedule should be within 1s of the configured backoff.
    assert abs(elapsed.total_seconds() - expected_delta.total_seconds()) < 1.0


def test_process_clone_failure_exhausts_attempts(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _seed_repo(session)
    job = enqueue_repo_sync(session, repo.id, max_attempts=2)
    job.status = "in_progress"
    job.attempts = 1  # one failure already recorded
    session.add(job)
    session.commit()

    def fake_sync(_session: Session, _repo: RegisteredRepo) -> Any:
        from ab_server.fetcher.worker import SyncReport

        return SyncReport(
            repo_id=str(_repo.id),
            commit_sha=None,
            inserted=0,
            skipped=0,
            rescored=0,
            errors=["clone_or_pull failed: 404"],
        )

    monkeypatch.setattr("ab_server.fetcher.worker.sync_repo", fake_sync)

    result = process_job(session, job)
    assert result.attempts == 2
    assert result.status == "failed"
    assert result.finished_at is not None


def test_process_repo_deleted_marks_failed(session: Session) -> None:
    repo = _seed_repo(session)
    job = enqueue_repo_sync(session, repo.id)
    job.status = "in_progress"
    session.add(job)
    session.commit()

    # Remove the repo before processing.
    session.delete(repo)
    session.commit()

    result = process_job(session, job)
    assert result.status == "failed"
    assert "not found" in (result.error or "")


def test_run_one_returns_none_when_empty(session: Session) -> None:
    assert run_one(session) is None


def test_run_one_processes_one(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _seed_repo(session)
    enqueue_repo_sync(session, repo.id)

    def fake_sync(_session: Session, _repo: RegisteredRepo) -> Any:
        from ab_server.fetcher.worker import SyncReport

        return SyncReport(
            repo_id=str(_repo.id),
            commit_sha="head",
            inserted=0,
            skipped=0,
            rescored=0,
            errors=[],
        )

    monkeypatch.setattr("ab_server.fetcher.worker.sync_repo", fake_sync)

    job = run_one(session)
    assert job is not None
    assert job.status == "done"
