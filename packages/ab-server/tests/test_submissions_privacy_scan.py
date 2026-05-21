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

_CLEAN_EVENTS = [
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
            {"name": "write_file", "args": {"path": "notes/greeting.txt", "content": "Hello.\n"}}
        ],
        "tool_returns": [{"path": "notes/greeting.txt", "content": "Hello.\n"}],
        "model_output": "ok",
        "vault_state_diff": None,
        "tokens_in": 1,
        "tokens_out": 1,
        "latency_ms": 1,
        "cost_usd": 0.0,
    },
    {
        "event": "run_end",
        "finished_at": "2026-05-21T12:00:01Z",
        "status": "completed",
        "totals": {"tokens_in": 1, "tokens_out": 1, "latency_ms": 1, "cost_usd": 0.0, "score": 1.0},
    },
]


def _events_with_token() -> list[dict]:
    events = json.loads(json.dumps(_CLEAN_EVENTS))
    leaked = "ghp_" + ("a" * 36)
    events[1]["model_output"] = f"Here is a token: {leaked}"
    return events


def _write_traj(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


@pytest.fixture()
def client_and_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, dict]]:
    cache_root = tmp_path / "cache"
    cache_root.mkdir(parents=True)
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(cache_root))

    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    ids = {}
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

        for label, events in (("clean", _CLEAN_EVENTS), ("dirty", _events_with_token())):
            source_path = f"results/{label}"
            traj_path = cache_root / str(repo.id) / source_path / "trajectory.jsonl"
            _write_traj(traj_path, events)

            submission = Submission(
                registered_repo_id=repo.id,
                source_commit_sha=f"sha-{label}",
                source_path=source_path,
                trust_tier="self_reported",
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
                score_total=1.0,
            )
            session.add(tr)
            session.commit()
            ids[label] = str(submission.id)

    def _override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)
    try:
        yield client, ids
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_privacy_scan_clean_trajectory(client_and_ids: tuple[TestClient, dict]) -> None:
    client, ids = client_and_ids
    resp = client.get(f"/api/v1/submissions/{ids['clean']}/privacy-scan")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["high_severity_hits"] == 0
    assert body["total_hits"] == 0
    assert body["hits"] == []


def test_privacy_scan_finds_github_token(client_and_ids: tuple[TestClient, dict]) -> None:
    client, ids = client_and_ids
    resp = client.get(f"/api/v1/submissions/{ids['dirty']}/privacy-scan")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["high_severity_hits"] >= 1
    assert body["total_hits"] >= 1
    assert any(h.get("pattern_id") == "github-token" for h in body["hits"])
