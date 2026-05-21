from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from ab_server.auth.github_oauth import reset_github_client, set_github_client
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
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


@pytest.fixture()
def github_mock(monkeypatch: pytest.MonkeyPatch) -> Iterator[httpx.MockTransport]:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "test-client-id")

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/device/code":
            return httpx.Response(
                200,
                json={
                    "device_code": "fake-device-code",
                    "user_code": "WXYZ-1234",
                    "verification_uri": "https://github.com/login/device",
                    "expires_in": 900,
                    "interval": 5,
                },
            )
        if request.url.path == "/login/oauth/access_token":
            return httpx.Response(
                200,
                json={
                    "access_token": "gho_FAKE",
                    "token_type": "bearer",
                    "scope": "read:user",
                },
            )
        if request.url.path == "/user":
            return httpx.Response(
                200,
                json={
                    "id": 4242,
                    "login": "alice",
                    "avatar_url": "https://example.com/alice.png",
                },
            )
        return httpx.Response(404, json={"detail": "unexpected path"})

    transport = httpx.MockTransport(_handler)
    client = httpx.Client(transport=transport)
    set_github_client(client)
    try:
        yield transport
    finally:
        reset_github_client()


def test_device_flow_creates_user_and_session(
    db_engine: object,
    github_mock: httpx.MockTransport,
) -> None:
    client = TestClient(app)

    start_resp = client.post("/api/v1/auth/github/device-start", json={})
    assert start_resp.status_code == 200, start_resp.text
    start_body = start_resp.json()
    assert start_body["device_code"] == "fake-device-code"

    poll_resp = client.post(
        "/api/v1/auth/github/device-poll",
        json={"device_code": "fake-device-code"},
    )
    assert poll_resp.status_code == 200, poll_resp.text
    body = poll_resp.json()
    assert body["github_login"] == "alice"
    assert body["access_token"]
    assert body["expires_at"]

    token = body["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["handle"] == "alice"

    with Session(db_engine) as session:  # type: ignore[arg-type]
        users = session.exec(select(User)).all()
        assert len(users) == 1
        assert users[0].github_id == "4242"
        assert users[0].session_token == token


def test_me_requires_token(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/me")
    assert resp.status_code == 401


def test_client_id_endpoint(db_engine: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_CLIENT_ID", "from-env-id")
    client = TestClient(app)
    resp = client.get("/api/v1/auth/github/client-id")
    assert resp.status_code == 200
    assert resp.json() == {"client_id": "from-env-id"}
