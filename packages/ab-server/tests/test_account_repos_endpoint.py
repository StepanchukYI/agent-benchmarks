from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    monkeypatch.setenv("AB_TEST_AUTH", "1")
    db_path = tmp_path / "account.db"
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


def _h(handle: str = "alice") -> dict[str, str]:
    return {"X-Test-User": handle}


def test_account_repos_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/account/repos")
    assert resp.status_code == 401


def test_account_repos_returns_user_repos(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/repos",
        json={"repo_url": "https://github.com/alice/r1", "default_branch": "main"},
        headers=_h("alice"),
    )
    assert created.status_code == 201
    client.post(
        "/api/v1/repos",
        json={"repo_url": "https://github.com/bob/r1"},
        headers=_h("bob"),
    )

    resp = client.get("/api/v1/account/repos", headers=_h("alice"))
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    expected = {
        "repo",
        "owner",
        "branch",
        "runs",
        "last_synced",
        "status",
        "error",
    }
    assert expected.issubset(item.keys())
    assert item["repo"] == "https://github.com/alice/r1"
    assert item["owner"] == "alice"
    assert item["branch"] == "main"
    assert item["last_synced"] == "never"
    assert item["status"] == "pending"
    assert item["runs"] == 0


def test_account_repos_isolates_users(db_engine: object) -> None:
    client = TestClient(app)
    client.post(
        "/api/v1/repos",
        json={"repo_url": "https://github.com/alice/r1"},
        headers=_h("alice"),
    )
    resp = client.get("/api/v1/account/repos", headers=_h("bob"))
    assert resp.status_code == 200
    assert resp.json() == []
