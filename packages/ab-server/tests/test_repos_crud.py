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
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
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


def _auth_headers(handle: str = "alice") -> dict[str, str]:
    return {"X-Test-User": handle}


def test_register_repo_returns_row(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/repos",
        json={"repo_url": "https://github.com/alice/results", "default_branch": "main", "is_public": True},
        headers=_auth_headers(),
    )
    assert resp.status_code == 201, resp.text
    row = resp.json()
    assert row["repo_url"] == "https://github.com/alice/results"
    assert row["status"] == "registered"
    assert row["is_public"] is True


def test_register_repo_idempotent_on_same_url(db_engine: object) -> None:
    client = TestClient(app)
    payload = {"repo_url": "https://github.com/alice/results"}
    first = client.post("/api/v1/repos", json=payload, headers=_auth_headers())
    second = client.post("/api/v1/repos", json=payload, headers=_auth_headers())
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_list_repos_returns_only_current_user(db_engine: object) -> None:
    client = TestClient(app)
    client.post(
        "/api/v1/repos",
        json={"repo_url": "https://github.com/alice/r1"},
        headers=_auth_headers("alice"),
    )
    client.post(
        "/api/v1/repos",
        json={"repo_url": "https://github.com/bob/r1"},
        headers=_auth_headers("bob"),
    )
    alice_list = client.get("/api/v1/repos", headers=_auth_headers("alice"))
    assert alice_list.status_code == 200
    rows = alice_list.json()
    assert len(rows) == 1
    assert rows[0]["repo_url"] == "https://github.com/alice/r1"


def test_delete_repo_archives(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/repos",
        json={"repo_url": "https://github.com/alice/r1"},
        headers=_auth_headers(),
    ).json()
    delete_resp = client.delete(f"/api/v1/repos/{created['id']}", headers=_auth_headers())
    assert delete_resp.status_code == 204
    listed = client.get("/api/v1/repos", headers=_auth_headers()).json()
    assert listed == []


def test_register_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post("/api/v1/repos", json={"repo_url": "https://github.com/alice/r1"})
    assert resp.status_code == 401
