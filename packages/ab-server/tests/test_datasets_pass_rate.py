"""Tests for _compute_task_stats pass_rate_30d using authoritative `passed` flag."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ab_server.api.datasets import _compute_task_stats
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_session(tmp_path: Path) -> Iterator[Session]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'datasets_pr.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_sub(session: Session, *, handle: str = "u1") -> Submission:
    user = User(github_id=f"gh-{handle}", handle=handle)
    session.add(user)
    session.commit()
    session.refresh(user)
    repo = RegisteredRepo(user_id=user.id, repo_url=f"https://github.com/{handle}/r")
    session.add(repo)
    session.commit()
    session.refresh(repo)
    sub = Submission(
        registered_repo_id=repo.id,
        source_commit_sha="abc",
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


def _make_tr(
    session: Session,
    *,
    sub: Submission,
    task_id: str = "L0_001",
    passed: bool | None,
    status: str = "completed",
    score_total: float = 0.5,
) -> None:
    tr = TaskResult(
        submission_id=sub.id,
        task_id=task_id,
        suite="L0_smoke",
        model="m1",
        tier="T0",
        tier_hash="abc",
        status=status,
        score_total=score_total,
        passed=passed,
    )
    session.add(tr)
    session.commit()


def test_pass_rate_mixed_uses_decided_denominator(db_session: Session) -> None:
    """2 passed, 1 failed, 1 None → pass_rate = 2/3 (decided=3, not total=4)."""
    sub = _make_sub(db_session)
    _make_tr(db_session, sub=sub, passed=True)
    _make_tr(db_session, sub=sub, passed=True)
    _make_tr(db_session, sub=sub, passed=False)
    _make_tr(db_session, sub=sub, passed=None)

    stats = _compute_task_stats(db_session, "L0_001")

    assert stats["runs_count_30d"] == 4
    assert stats["pass_rate_30d"] is not None
    assert abs(stats["pass_rate_30d"] - 2 / 3) < 1e-9


def test_pass_rate_all_none_is_none_not_zero(db_session: Session) -> None:
    """All passed=None → pass_rate_30d is None (not measured), not 0."""
    sub = _make_sub(db_session, handle="u2")
    _make_tr(db_session, sub=sub, passed=None)
    _make_tr(db_session, sub=sub, passed=None)

    stats = _compute_task_stats(db_session, "L0_001")

    assert stats["runs_count_30d"] == 2
    assert stats["pass_rate_30d"] is None


def test_pass_rate_status_irrelevant(db_session: Session) -> None:
    """pass_rate must not depend on status value — 'completed' or 'passed'/'failed'."""
    sub = _make_sub(db_session, handle="u3")
    # Row with status="completed" (script path) but passed=True
    _make_tr(db_session, sub=sub, passed=True, status="completed")
    # Row with status="passed" (fetcher path) but passed=False
    _make_tr(db_session, sub=sub, passed=False, status="passed")

    stats = _compute_task_stats(db_session, "L0_001")

    # 1 passed out of 2 decided — 0.5 regardless of status strings
    assert stats["pass_rate_30d"] is not None
    assert abs(stats["pass_rate_30d"] - 0.5) < 1e-9
