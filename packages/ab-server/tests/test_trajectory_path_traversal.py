"""C1 regression: a user-controlled source_path with traversal segments
must not let the server read files outside the registered repo's clone dir.

We register a submission whose source_path is `../../etc` and request its
trajectory. resolve_submission_paths must reject the request with 400 long
before any filesystem read.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


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

        submission = Submission(
            registered_repo_id=repo.id,
            source_commit_sha="sha-1",
            # Hostile source_path: would resolve to /etc/trajectory.jsonl
            # if the path joiner didn't enforce containment.
            source_path="../../etc",
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


def test_submission_trajectory_traversal_returns_400(
    setup: tuple[TestClient, dict],
) -> None:
    client, ctx = setup
    sid = ctx["submission_id"]
    resp = client.get(f"/api/v1/submissions/{sid}/trajectory")
    assert resp.status_code == 400, resp.text
    assert "invalid source path" in resp.json().get("detail", "").lower()


def test_submission_privacy_scan_traversal_returns_400(
    setup: tuple[TestClient, dict],
) -> None:
    client, ctx = setup
    sid = ctx["submission_id"]
    resp = client.get(f"/api/v1/submissions/{sid}/privacy-scan")
    assert resp.status_code == 400, resp.text
    assert "invalid source path" in resp.json().get("detail", "").lower()
