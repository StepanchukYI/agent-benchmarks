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


def _write_trajectory(path: Path, *, task_id: str, model: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "event": "run_start",
            "run_id": "r1",
            "task_id": task_id,
            "model": model,
            "harness": "claude-code-cli@0.4.1",
            "tier": "T0",
            "tier_hash": "sha256:0",
            "dataset_version": "ab-datasets==0.0.1",
            "started_at": "2026-05-21T12:00:00Z",
        },
        {
            "event": "turn",
            "idx": 0,
            "role": "assistant",
            "tool_calls": [
                {"name": "write_file", "args": {"path": "notes/x.txt", "content": "hi\n"}}
            ],
            "tool_returns": [{"path": "notes/x.txt", "content": "hi\n"}],
            "model_output": "wrote file",
            "vault_state_diff": {"created": ["notes/x.txt"], "modified": [], "deleted": []},
            "tokens_in": 12,
            "tokens_out": 6,
            "latency_ms": 100,
            "cost_usd": 0.0,
        },
        {
            "event": "scorer",
            "scorer_name": "file_diff",
            "kind": "deterministic",
            "pass": True,
            "score": 1.0,
            "detail": {"diff": []},
        },
        {
            "event": "run_end",
            "finished_at": "2026-05-21T12:00:14Z",
            "status": "completed",
            "totals": {"tokens_in": 12, "tokens_out": 6, "latency_ms": 100, "cost_usd": 0.0, "score": 1.0},
        },
    ]
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _make_engine(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _client(engine) -> TestClient:
    def _override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    return TestClient(app)


def _add_submission(
    session: Session,
    cache_root: Path,
    *,
    handle: str,
    is_public: bool,
    task_id: str,
    model: str,
    ingested_at: datetime,
) -> None:
    user = User(github_id=f"gh-{handle}", handle=handle, avatar_url=None)
    session.add(user)
    session.commit()
    session.refresh(user)
    repo = RegisteredRepo(
        user_id=user.id,
        repo_url=f"https://github.com/{handle}/results",
        default_branch="main",
        is_public=is_public,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)

    source_path = f"results/{task_id}-{handle}"
    traj_path = cache_root / str(repo.id) / source_path / "trajectory.jsonl"
    _write_trajectory(traj_path, task_id=task_id, model=model)

    submission = Submission(
        registered_repo_id=repo.id,
        source_commit_sha=f"sha-{handle}",
        source_path=source_path,
        trust_tier="verified",
        model=model,
        tier="T0",
        dataset_version="ab-datasets==0.0.1",
        ingested_at=ingested_at,
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)

    tr = TaskResult(
        submission_id=submission.id,
        task_id=task_id,
        suite="file-ops",
        model=model,
        tier="T0",
        tier_hash="sha256:0",
        status="completed",
        score_correctness=0.9,
        score_context_eff=0.8,
        score_tool_skill=0.7,
        score_memory=0.6,
        score_latency=0.5,
        score_total=1.0,
    )
    session.add(tr)
    session.commit()


def test_default_returns_most_recent_public(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir(parents=True)
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(cache_root))
    engine = _make_engine(tmp_path)
    now = datetime.now(UTC)
    with Session(engine) as session:
        _add_submission(
            session,
            cache_root,
            handle="alice",
            is_public=True,
            task_id="L0_001",
            model="claude-sonnet",
            ingested_at=now - timedelta(days=2),
        )
        _add_submission(
            session,
            cache_root,
            handle="bob",
            is_public=True,
            task_id="L0_002",
            model="claude-haiku",
            ingested_at=now,
        )

    client = _client(engine)
    try:
        resp = client.get("/api/v1/trajectories/default")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Most-recent public submission is bob's (L0_002 / haiku).
        assert body["header"]["task_id"] == "L0_002"
        assert body["header"]["model"] == "claude-haiku"
        assert body["trust"]["tier"] == "verified"
        assert len(body["turns"]) == 1
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_default_404_when_no_public_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir(parents=True)
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(cache_root))
    engine = _make_engine(tmp_path)
    client = _client(engine)
    try:
        resp = client.get("/api/v1/trajectories/default")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "no public trajectory available"
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_default_skips_private_repo_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_root = tmp_path / "cache"
    cache_root.mkdir(parents=True)
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(cache_root))
    engine = _make_engine(tmp_path)
    now = datetime.now(UTC)
    with Session(engine) as session:
        # Private submission is the most-recent overall — must NOT be picked.
        _add_submission(
            session,
            cache_root,
            handle="carol",
            is_public=False,
            task_id="L0_777",
            model="claude-private",
            ingested_at=now,
        )
        # Older public submission is the only eligible one.
        _add_submission(
            session,
            cache_root,
            handle="dave",
            is_public=True,
            task_id="L0_001",
            model="claude-sonnet",
            ingested_at=now - timedelta(days=5),
        )

    client = _client(engine)
    try:
        resp = client.get("/api/v1/trajectories/default")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["header"]["task_id"] == "L0_001"
        assert body["header"]["model"] == "claude-sonnet"
    finally:
        app.dependency_overrides.pop(get_session, None)
