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


def _payload(name: str = "L1 regression watchdog") -> dict[str, object]:
    return {
        "name": name,
        "metric": "score_total",
        "suite": "L1_memory",
        "model": None,
        "tier": "T2",
        "direction": "down",
        "threshold_pct": 5.0,
        "window_days": 7,
        "channels": [{"type": "email", "target": "alice@example.com"}],
        "enabled": True,
    }


def test_create_returns_state_idle(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post("/api/v1/alerts", json=_payload(), headers=_h())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["state"] == "idle"
    assert body["channels"] == [{"type": "email", "target": "alice@example.com"}]


def test_list_then_patch_then_delete(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post("/api/v1/alerts", json=_payload(), headers=_h()).json()

    listed = client.get("/api/v1/alerts", headers=_h()).json()
    assert len(listed) == 1

    patch = client.patch(
        f"/api/v1/alerts/{created['id']}",
        json={"threshold_pct": 10.0, "enabled": False},
        headers=_h(),
    )
    assert patch.status_code == 200
    assert patch.json()["threshold_pct"] == 10.0
    assert patch.json()["enabled"] is False

    delete = client.delete(f"/api/v1/alerts/{created['id']}", headers=_h())
    assert delete.status_code == 204
    assert client.get("/api/v1/alerts", headers=_h()).json() == []


def test_invalid_direction_rejected(db_engine: object) -> None:
    client = TestClient(app)
    bad = _payload()
    bad["direction"] = "sideways"
    resp = client.post("/api/v1/alerts", json=bad, headers=_h())
    assert resp.status_code == 400


def test_invalid_window_days_rejected(db_engine: object) -> None:
    client = TestClient(app)
    bad = _payload()
    bad["window_days"] = 0
    resp = client.post("/api/v1/alerts", json=bad, headers=_h())
    assert resp.status_code == 400


def test_alerts_isolated_per_user(db_engine: object) -> None:
    client = TestClient(app)
    client.post("/api/v1/alerts", json=_payload("alice-rule"), headers=_h("alice"))
    client.post("/api/v1/alerts", json=_payload("bob-rule"), headers=_h("bob"))
    alice = client.get("/api/v1/alerts", headers=_h("alice")).json()
    bob = client.get("/api/v1/alerts", headers=_h("bob")).json()
    assert len(alice) == 1 and alice[0]["name"] == "alice-rule"
    assert len(bob) == 1 and bob[0]["name"] == "bob-rule"


def test_alerts_require_auth(db_engine: object) -> None:
    client = TestClient(app)
    assert client.post("/api/v1/alerts", json=_payload()).status_code == 401
    assert client.get("/api/v1/alerts").status_code == 401
    assert client.post("/api/v1/alerts/evaluate").status_code == 401
