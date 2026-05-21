from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


def _write_trajectory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    events = [
        {
            "event": "run_start",
            "run_id": "r1",
            "task_id": "L0_001",
            "model": "claude-sonnet",
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
                {
                    "name": "write_file",
                    "args": {"path": "notes/greeting.txt", "content": "Hello, Example.\n"},
                }
            ],
            "tool_returns": [{"path": "notes/greeting.txt", "content": "Hello, Example.\n"}],
            "model_output": "wrote file",
            "vault_state_diff": {"created": ["notes/greeting.txt"], "modified": [], "deleted": []},
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


@pytest.fixture()
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, dict]]:
    cache_root = tmp_path / "cache"
    cache_root.mkdir(parents=True)
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(cache_root))

    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(github_id="u1", handle="alice", avatar_url=None)
        session.add(user)
        session.commit()
        session.refresh(user)
        repo = RegisteredRepo(
            user_id=user.id,
            repo_url="https://github.com/alice/results",
            default_branch="main",
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)

        source_path = "results/20260521T000000Z-run-1"
        repo_clone = cache_root / str(repo.id)
        traj_path = repo_clone / source_path / "trajectory.jsonl"
        _write_trajectory(traj_path)

        submission = Submission(
            registered_repo_id=repo.id,
            source_commit_sha="sha-1",
            source_path=source_path,
            trust_tier="verified",
            model="claude-sonnet",
            tier="T0",
            dataset_version="ab-datasets==0.0.1",
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)

        tr = TaskResult(
            submission_id=submission.id,
            task_id="L0_001",
            suite="file-ops",
            model="claude-sonnet",
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

        submission_id = str(submission.id)

    def _override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)
    try:
        yield client, {"submission_id": submission_id}
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_get_trajectory_via_submission_id(setup: tuple[TestClient, dict]) -> None:
    client, ctx = setup
    sid = ctx["submission_id"]
    resp = client.get(f"/api/v1/runs/{sid}/trajectories/L0_001")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["header"]["task_id"] == "L0_001"
    assert body["header"]["model"] == "claude-sonnet"
    assert body["header"]["status"] == "completed"
    assert len(body["turns"]) == 1
    assert body["turns"][0]["tool_calls"][0]["name"] == "write_file"
    assert len(body["scorers"]) == 1
    assert body["scorers"][0]["scorer_name"] == "file_diff"
    assert body["trust"]["tier"] == "verified"
    assert body["pillars"]["correctness"] == 0.9


def test_get_trajectory_unknown_id_returns_404(setup: tuple[TestClient, dict]) -> None:
    client, _ = setup
    resp = client.get("/api/v1/runs/00000000-0000-0000-0000-000000000000/trajectories/L0_001")
    assert resp.status_code == 404


def test_submission_trajectory_alias(setup: tuple[TestClient, dict]) -> None:
    client, ctx = setup
    sid = ctx["submission_id"]
    resp = client.get(f"/api/v1/submissions/{sid}/trajectory")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["header"]["task_id"] == "L0_001"
    assert body["trust"]["tier"] == "verified"
