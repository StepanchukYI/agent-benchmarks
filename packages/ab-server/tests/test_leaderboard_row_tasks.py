"""Tests for GET /leaderboard/row/tasks endpoint (B4)."""
from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "row_tasks.db"
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


@pytest.fixture()
def client(db_engine: object) -> TestClient:
    return TestClient(app)


def _make_user_repo_sub(
    session: Session,
    *,
    handle: str,
    model: str = "m1",
    tier: str = "T0",
    hours_ago: float = 1.0,
    archived: bool = False,
) -> tuple[User, RegisteredRepo, Submission]:
    user = User(github_id=f"gh-{handle}", handle=handle)
    session.add(user)
    session.commit()
    session.refresh(user)
    repo = RegisteredRepo(
        user_id=user.id,
        repo_url=f"https://github.com/{handle}/r",
        status="archived" if archived else "active",
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    sub = Submission(
        registered_repo_id=repo.id,
        source_commit_sha="abc123",
        source_path="results/x",
        trust_tier="self_reported",
        ingested_at=datetime.now(UTC) - timedelta(hours=hours_ago),
        model=model,
        tier=tier,
        dataset_version="0.0.1",
    )
    session.add(sub)
    session.commit()
    session.refresh(sub)
    return user, repo, sub


def _make_tr(
    session: Session,
    *,
    sub: Submission,
    task_id: str = "L0_001",
    suite: str = "L0_smoke",
    passed: bool | None = True,
    traj_path: str | None = None,
) -> TaskResult:
    tr = TaskResult(
        submission_id=sub.id,
        task_id=task_id,
        suite=suite,
        model=sub.model,
        tier=sub.tier,
        tier_hash="abc",
        status="completed",
        score_total=0.8,
        score_correctness=0.8,
        passed=passed,
        trajectory_blob_ref=traj_path,
    )
    session.add(tr)
    session.commit()
    session.refresh(tr)
    return tr


def test_dedup_keeps_most_recent(db_engine: object, client: TestClient, tmp_path: Path) -> None:
    """Two TaskResults for the same task_id → only the most-recent appears."""
    with Session(db_engine) as session:
        # One user, two separate submissions (e.g. two sweeps) at different times
        _user, repo, sub_old = _make_user_repo_sub(session, handle="alice", hours_ago=5.0)
        sub_new = Submission(
            registered_repo_id=repo.id,
            source_commit_sha="def456",
            source_path="results/y",
            trust_tier="self_reported",
            ingested_at=datetime.now(UTC) - timedelta(hours=1.0),
            model="m1",
            tier="T0",
            dataset_version="0.0.1",
        )
        session.add(sub_new)
        session.commit()
        session.refresh(sub_new)
        _make_tr(session, sub=sub_old, task_id="L0_001", passed=False)
        _make_tr(session, sub=sub_new, task_id="L0_001", passed=True)

    resp = client.get("/api/v1/leaderboard/row/tasks?model=m1&operator=alice&tier=T0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["task_id"] == "L0_001"
    # Most-recent run: passed=True
    assert data[0]["passed"] is True


def test_passed_none_when_no_decided_scorers(
    db_engine: object, client: TestClient
) -> None:
    """passed=None propagates to the response when no scorer decided."""
    with Session(db_engine) as session:
        _, _, sub = _make_user_repo_sub(session, handle="bob")
        _make_tr(session, sub=sub, task_id="L0_002", passed=None)

    resp = client.get("/api/v1/leaderboard/row/tasks?model=m1&operator=bob&tier=T0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["passed"] is None


def test_archived_repo_excluded(db_engine: object, client: TestClient) -> None:
    """TaskResults from archived repos must not appear."""
    with Session(db_engine) as session:
        _, _, sub = _make_user_repo_sub(session, handle="carol", archived=True)
        _make_tr(session, sub=sub, task_id="L0_003", passed=True)

    resp = client.get("/api/v1/leaderboard/row/tasks?model=m1&operator=carol&tier=T0")
    assert resp.status_code == 200
    assert resp.json() == []


def test_operator_filter_isolates(db_engine: object, client: TestClient) -> None:
    """A different operator's run for the same model+tier must not appear."""
    with Session(db_engine) as session:
        _, _, sub_a = _make_user_repo_sub(session, handle="alice")
        _, _, sub_b = _make_user_repo_sub(session, handle="dave")
        _make_tr(session, sub=sub_a, task_id="L0_001", passed=True)
        _make_tr(session, sub=sub_b, task_id="L0_002", passed=True)

    resp = client.get("/api/v1/leaderboard/row/tasks?model=m1&operator=alice&tier=T0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["task_id"] == "L0_001"


def test_scorers_read_from_trajectory(
    db_engine: object, client: TestClient, tmp_path: Path
) -> None:
    """Scorer events in trajectory.jsonl surface in response scorers array."""
    traj_file = tmp_path / "trajectory.jsonl"
    scorer_line = json.dumps(
        {
            "event": "scorer",
            "scorer_name": "exact_match",
            "kind": "deterministic",
            "pass": True,
            "score": 1.0,
            "detail": "matched",
        }
    )
    traj_file.write_text(scorer_line + "\n")

    with Session(db_engine) as session:
        _, _, sub = _make_user_repo_sub(session, handle="eve")
        _make_tr(session, sub=sub, task_id="L0_004", passed=True, traj_path=str(traj_file))

    resp = client.get("/api/v1/leaderboard/row/tasks?model=m1&operator=eve&tier=T0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert len(data[0]["scorers"]) == 1
    scorer = data[0]["scorers"][0]
    assert scorer["name"] == "exact_match"
    assert scorer["pass"] is True
    assert scorer["score"] == 1.0
