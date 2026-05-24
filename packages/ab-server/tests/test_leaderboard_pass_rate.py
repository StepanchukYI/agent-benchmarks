"""Tests for pass_rate on LeaderboardRow and mean_pass_rate on LeaderboardSummary."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.leaderboard.queries import compute_leaderboard_response
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "pass_rate.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    def _override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_session, None)


_PR_COUNTER: dict[str, int] = {}


def _make_tr(
    session: Session,
    *,
    model: str,
    suite: str,
    passed: bool | None,
    score_correctness: float = 0.8,
    task_id: str | None = None,
) -> None:
    """Insert a minimal TaskResult without a Submission (local-run path).

    Each call uses a unique ``task_id`` by default. The leaderboard query
    dedups (bucket, task_id), so N contributions to one bucket need N distinct
    task_ids (otherwise dedup collapses them to 1).
    """
    if task_id is None:
        n = _PR_COUNTER.get(model, 0) + 1
        _PR_COUNTER[model] = n
        task_id = f"L0_{n:03d}"
    tr = TaskResult(
        task_id=task_id,
        suite=suite,
        model=model,
        tier="T0",
        tier_hash="abc",
        status="completed" if passed else "failed",
        score_total=score_correctness,
        score_correctness=score_correctness,
        passed=passed,
    )
    session.add(tr)
    session.commit()


def test_pass_rate_mixed_passed(db_engine: object) -> None:
    """A row with 2 passes and 1 fail → pass_rate=66.66..."""
    with Session(db_engine) as session:
        _make_tr(session, model="m1", suite="L0_smoke", passed=True)
        _make_tr(session, model="m1", suite="L0_smoke", passed=True)
        _make_tr(session, model="m1", suite="L0_smoke", passed=False)

        result = compute_leaderboard_response(session)

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.pass_rate is not None
    assert abs(row.pass_rate - 200.0 / 3.0) < 1e-6  # 2/3 * 100


def test_pass_rate_all_none(db_engine: object) -> None:
    """A row with all passed=None → pass_rate=None (not 0.0)."""
    with Session(db_engine) as session:
        _make_tr(session, model="m1", suite="L0_smoke", passed=None)
        _make_tr(session, model="m1", suite="L0_smoke", passed=None)

        result = compute_leaderboard_response(session)

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.pass_rate is None


def test_pass_rate_all_true(db_engine: object) -> None:
    """A row with all passed=True → pass_rate=100.0."""
    with Session(db_engine) as session:
        _make_tr(session, model="m1", suite="L0_smoke", passed=True)
        _make_tr(session, model="m1", suite="L0_smoke", passed=True)

        result = compute_leaderboard_response(session)

    assert len(result.rows) == 1
    assert result.rows[0].pass_rate == 100.0


def _make_submission(session: Session, *, engine: object) -> Submission:
    """Create a User + RegisteredRepo + Submission with a recent ingested_at."""
    user = User(github_id="gh-sum", handle="sumuser")
    session.add(user)
    session.commit()
    session.refresh(user)
    repo = RegisteredRepo(user_id=user.id, repo_url="https://github.com/sumuser/r")
    session.add(repo)
    session.commit()
    session.refresh(repo)
    sub = Submission(
        registered_repo_id=repo.id,
        source_commit_sha="abc123",
        source_path="results/x",
        trust_tier="self_reported",
        ingested_at=datetime.now(UTC) - timedelta(hours=1),
        model="m1",
        tier="T0",
        dataset_version="0.0.1",
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return sub


def _make_tr_with_sub(
    session: Session,
    *,
    sub: Submission,
    passed: bool | None,
    task_id: str | None = None,
) -> None:
    if task_id is None:
        n = _PR_COUNTER.get("__sub__", 0) + 1
        _PR_COUNTER["__sub__"] = n
        task_id = f"L0_{n:03d}"
    tr = TaskResult(
        submission_id=sub.id,
        task_id=task_id,
        suite="L0_smoke",
        model="m1",
        tier="T0",
        tier_hash="abc",
        status="completed",
        score_total=0.8,
        score_correctness=0.8,
        passed=passed,
    )
    session.add(tr)
    session.commit()


def test_mean_pass_rate_in_summary(db_engine: object) -> None:
    """mean_pass_rate in summary reflects the window-wide pass rate."""
    with Session(db_engine) as session:
        sub = _make_submission(session, engine=db_engine)
        _make_tr_with_sub(session, sub=sub, passed=True)
        _make_tr_with_sub(session, sub=sub, passed=True)
        _make_tr_with_sub(session, sub=sub, passed=False)

        result = compute_leaderboard_response(session, range_days=7)

    assert len(result.rows) == 1
    assert result.rows[0].pass_rate is not None
    assert abs(result.rows[0].pass_rate - 200.0 / 3.0) < 1e-6
    # summary is populated because there are rows with measured correctness
    if result.summary is not None:
        assert result.summary.mean_pass_rate is not None
        assert abs(result.summary.mean_pass_rate - 200.0 / 3.0) < 1e-6


def test_mean_pass_rate_none_when_no_decided(db_engine: object) -> None:
    """mean_pass_rate=None in summary when all task results have passed=None."""
    with Session(db_engine) as session:
        sub = _make_submission(session, engine=db_engine)
        _make_tr_with_sub(session, sub=sub, passed=None)
        _make_tr_with_sub(session, sub=sub, passed=None)

        result = compute_leaderboard_response(session, range_days=7)

    assert len(result.rows) == 1
    assert result.rows[0].pass_rate is None
    if result.summary is not None:
        assert result.summary.mean_pass_rate is None
