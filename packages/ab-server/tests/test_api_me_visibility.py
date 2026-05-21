"""GET /api/v1/me + PATCH /api/v1/me/visibility regression.

Confirms /me returns the new visibility fields with defaults, that PATCH
partially updates them, and that unauthenticated callers get 401.
"""

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


def _mint_token(client: TestClient) -> str:
    start_resp = client.post("/api/v1/auth/github/device-start", json={})
    assert start_resp.status_code == 200, start_resp.text
    poll_resp = client.post(
        "/api/v1/auth/github/device-poll",
        json={"device_code": "fake-device-code"},
    )
    assert poll_resp.status_code == 200, poll_resp.text
    return poll_resp.json()["access_token"]


def test_me_returns_visibility_defaults(
    db_engine: object,
    github_mock: httpx.MockTransport,
) -> None:
    client = TestClient(app)
    token = _mint_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["handle"] == "alice"
    assert body["public_profile"] is True
    assert body["share_runs"] is True


def test_patch_me_visibility_partial_update(
    db_engine: object,
    github_mock: httpx.MockTransport,
) -> None:
    client = TestClient(app)
    token = _mint_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    # Flip only share_runs; public_profile must stay at default True.
    resp = client.patch(
        "/api/v1/me/visibility",
        headers=headers,
        json={"share_runs": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["public_profile"] is True
    assert body["share_runs"] is False

    # Now flip public_profile too.
    resp2 = client.patch(
        "/api/v1/me/visibility",
        headers=headers,
        json={"public_profile": False},
    )
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert body2["public_profile"] is False
    assert body2["share_runs"] is False

    # DB reflects the toggles.
    with Session(db_engine) as session:  # type: ignore[arg-type]
        users = session.exec(select(User)).all()
        assert len(users) == 1
        assert users[0].public_profile is False
        assert users[0].share_runs is False

    # GET /me reflects the persisted values.
    me_resp = client.get("/api/v1/me", headers=headers)
    assert me_resp.status_code == 200
    me_body = me_resp.json()
    assert me_body["public_profile"] is False
    assert me_body["share_runs"] is False


def test_patch_me_visibility_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.patch(
        "/api/v1/me/visibility",
        json={"public_profile": False},
    )
    assert resp.status_code == 401
