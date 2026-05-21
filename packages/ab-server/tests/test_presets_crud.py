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


def _h(user: str = "alice") -> dict[str, str]:
    return {"X-Test-User": user}


def _payload(name: str = "default") -> dict[str, object]:
    return {
        "name": name,
        "suites": ["L0_smoke"],
        "task_ids": ["L0_001", "L0_002"],
        "models": ["claude-sonnet-4-5"],
        "tier": "T2",
        "repetitions": 1,
        "sandbox": "local",
        "concurrency": 2,
    }


def test_create_then_list(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post("/api/v1/presets", json=_payload(), headers=_h())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "default"
    assert body["tier"] == "T2"
    assert body["task_ids"] == ["L0_001", "L0_002"]

    listed = client.get("/api/v1/presets", headers=_h()).json()
    assert len(listed) == 1
    assert listed[0]["id"] == body["id"]


def test_create_idempotent_on_user_name(db_engine: object) -> None:
    client = TestClient(app)
    first = client.post("/api/v1/presets", json=_payload(), headers=_h()).json()
    updated_payload = _payload()
    updated_payload["concurrency"] = 8
    second = client.post("/api/v1/presets", json=updated_payload, headers=_h()).json()
    assert first["id"] == second["id"]
    assert second["concurrency"] == 8


def test_delete(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post("/api/v1/presets", json=_payload(), headers=_h()).json()
    resp = client.delete(f"/api/v1/presets/{created['id']}", headers=_h())
    assert resp.status_code == 204
    assert client.get("/api/v1/presets", headers=_h()).json() == []


def test_presets_isolated_per_user(db_engine: object) -> None:
    client = TestClient(app)
    client.post("/api/v1/presets", json=_payload("alice-pref"), headers=_h("alice"))
    client.post("/api/v1/presets", json=_payload("bob-pref"), headers=_h("bob"))
    alice = client.get("/api/v1/presets", headers=_h("alice")).json()
    bob = client.get("/api/v1/presets", headers=_h("bob")).json()
    assert len(alice) == 1 and alice[0]["name"] == "alice-pref"
    assert len(bob) == 1 and bob[0]["name"] == "bob-pref"


def test_presets_require_auth(db_engine: object) -> None:
    client = TestClient(app)
    assert client.post("/api/v1/presets", json=_payload()).status_code == 401
    assert client.get("/api/v1/presets").status_code == 401


def test_delete_other_users_preset_is_404(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post("/api/v1/presets", json=_payload(), headers=_h("alice")).json()
    resp = client.delete(f"/api/v1/presets/{created['id']}", headers=_h("bob"))
    assert resp.status_code == 404
