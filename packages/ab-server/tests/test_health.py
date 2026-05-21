from __future__ import annotations

from ab_server.main import app
from fastapi.testclient import TestClient


def test_healthz_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_server_and_ab_datasets() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/version")
    assert response.status_code == 200
    payload = response.json()
    assert "server" in payload
    assert "ab_datasets" in payload
    assert isinstance(payload["server"], str)
    assert isinstance(payload["ab_datasets"], str)
