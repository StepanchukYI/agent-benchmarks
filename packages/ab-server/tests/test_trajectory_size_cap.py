"""M_T regression: oversized trajectories must be refused with 413 before
the server reads them into memory.

We don't actually allocate 100 MiB on disk — we monkeypatch
``Path.stat().st_size`` for the candidate path to report a value above
``_TRAJECTORY_MAX_BYTES``. The endpoint should then 413 without opening
the file.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.api import _trajectory_view
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


def _write_minimal_trajectory(path: Path) -> None:
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
            "event": "run_end",
            "finished_at": "2026-05-21T12:00:14Z",
            "status": "completed",
            "totals": {
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
                "score": 0.0,
            },
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
        _write_minimal_trajectory(traj_path)

        submission = Submission(
            registered_repo_id=repo.id,
            source_commit_sha="sha-1",
            source_path=source_path,
            trust_tier="self_reported",
            model="claude-sonnet",
            tier="T0",
            dataset_version="ab-datasets==0.0.1",
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)
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


def test_oversized_trajectory_returns_413(
    setup: tuple[TestClient, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, ctx = setup
    sid = ctx["submission_id"]

    # Force Path.stat() to report a size above the 100 MiB cap.
    # We only override for trajectory.jsonl so other paths (e.g. db) work.
    real_stat = Path.stat
    oversize = _trajectory_view._TRAJECTORY_MAX_BYTES + 1

    def fake_stat(self: Path, *args: object, **kwargs: object) -> os.stat_result:
        if self.name == "trajectory.jsonl":
            base = real_stat(self, *args, **kwargs)  # type: ignore[arg-type]
            # stat_result is immutable; build a replacement tuple.
            fields = list(base)
            # st_size is index 6 in the 10-tuple.
            fields[6] = oversize
            return os.stat_result(tuple(fields))
        return real_stat(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "stat", fake_stat)

    resp = client.get(f"/api/v1/submissions/{sid}/trajectory")
    assert resp.status_code == 413, resp.text
    assert "too large" in resp.json().get("detail", "").lower()
