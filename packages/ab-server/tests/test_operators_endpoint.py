from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "ops.db"
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


def _seed(engine: object) -> None:
    with Session(engine) as session:
        alice = User(github_id="gh-a", handle="alice")
        bob = User(github_id="gh-b", handle="bob")
        session.add_all([alice, bob])
        session.commit()
        session.refresh(alice)
        session.refresh(bob)

        repo_a = RegisteredRepo(user_id=alice.id, repo_url="https://github.com/alice/r")
        repo_b = RegisteredRepo(user_id=bob.id, repo_url="https://github.com/bob/r")
        session.add_all([repo_a, repo_b])
        session.commit()
        session.refresh(repo_a)
        session.refresh(repo_b)

        for repo, trust in [(repo_a, "verified"), (repo_b, "self_reported")]:
            sub = Submission(
                registered_repo_id=repo.id,
                source_commit_sha=f"sha-{repo.id}",
                source_path="results/x",
                trust_tier=trust,
                ingested_at=datetime.now(UTC),
                model="claude-sonnet-4-5",
                tier="T2",
                dataset_version="0.1.0",
            )
            session.add(sub)
        session.commit()


def test_operators_endpoint_returns_list(db_engine: object) -> None:
    _seed(db_engine)
    client = TestClient(app)
    resp = client.get("/api/v1/operators")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list)
    handles = {item["handle"] for item in items}
    assert {"self", "alice", "bob"}.issubset(handles)

    alice = next(i for i in items if i["handle"] == "alice")
    expected_keys = {
        "handle",
        "name",
        "initials",
        "color",
        "repo",
        "trust_default",
        "is_self",
    }
    assert expected_keys.issubset(alice.keys())
    assert alice["initials"] == "AL"
    assert alice["color"].startswith("#")
    assert alice["repo"] == "https://github.com/alice/r"
    assert alice["trust_default"] == "verified"
    assert alice["is_self"] is False

    self_op = next(i for i in items if i["handle"] == "self")
    assert self_op["is_self"] is True


def test_operators_endpoint_empty_db_returns_self_only(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/operators")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["handle"] == "self"
    assert items[0]["is_self"] is True
