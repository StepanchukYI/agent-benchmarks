"""list_submissions must not leak rows from private repos via operator filter."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # User with a PUBLIC repo + one submission.
        pub_user = User(github_id="u-pub", handle="pubuser", avatar_url=None)
        session.add(pub_user)
        session.commit()
        session.refresh(pub_user)
        pub_repo = RegisteredRepo(
            user_id=pub_user.id,
            repo_url="https://github.com/pubuser/results",
            default_branch="main",
            is_public=True,
            status="registered",
        )
        session.add(pub_repo)
        session.commit()
        session.refresh(pub_repo)
        pub_sub = Submission(
            registered_repo_id=pub_repo.id,
            source_commit_sha="sha-pub",
            source_path="results/pub-run",
            trust_tier="self_reported",
            model="claude-sonnet",
            tier="T0",
            dataset_version="ab-datasets==0.0.1",
        )
        session.add(pub_sub)
        session.commit()
        session.refresh(pub_sub)
        session.add(
            TaskResult(
                submission_id=pub_sub.id,
                task_id="L0_001",
                suite="file-ops",
                model="claude-sonnet",
                tier="T0",
                tier_hash="sha256:0",
                status="completed",
                score_total=1.0,
            )
        )

        # User with a PRIVATE repo + one submission. Must NOT surface.
        priv_user = User(github_id="u-priv", handle="privuser", avatar_url=None)
        session.add(priv_user)
        session.commit()
        session.refresh(priv_user)
        priv_repo = RegisteredRepo(
            user_id=priv_user.id,
            repo_url="https://github.com/privuser/results",
            default_branch="main",
            is_public=False,
            status="registered",
        )
        session.add(priv_repo)
        session.commit()
        session.refresh(priv_repo)
        priv_sub = Submission(
            registered_repo_id=priv_repo.id,
            source_commit_sha="sha-priv",
            source_path="results/priv-run",
            trust_tier="self_reported",
            model="claude-sonnet",
            tier="T0",
            dataset_version="ab-datasets==0.0.1",
        )
        session.add(priv_sub)
        session.commit()
        session.refresh(priv_sub)
        session.add(
            TaskResult(
                submission_id=priv_sub.id,
                task_id="L0_001",
                suite="file-ops",
                model="claude-sonnet",
                tier="T0",
                tier_hash="sha256:0",
                status="completed",
                score_total=0.5,
            )
        )
        session.commit()

    def _override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_list_submissions_operator_only_returns_public(client: TestClient) -> None:
    resp = client.get("/api/v1/submissions", params={"operator": "pubuser"})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["source_commit_sha"] == "sha-pub"


def test_list_submissions_operator_hides_private(client: TestClient) -> None:
    resp = client.get("/api/v1/submissions", params={"operator": "privuser"})
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert items == [], (
        f"Private repo submissions must not leak via operator filter; got: {items}"
    )
