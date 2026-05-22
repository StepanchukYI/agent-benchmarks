"""L_S regression: POST /api/v1/auth/logout invalidates the caller's session.

We end-to-end the device flow to mint a real token, hit /me to confirm the
token is live, POST /auth/logout, then confirm /me returns 401 and the
backing AuthSession row is gone — while a second concurrent session for the
same user keeps working.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from ab_server.auth.github_oauth import (
    hash_session_token,
    reset_github_client,
    set_github_client,
)
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import AuthSession, User
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


def test_logout_invalidates_only_used_session(
    db_engine: object,
    github_mock: httpx.MockTransport,
) -> None:
    """Two concurrent sessions for one user; logout kills only the one used."""
    client = TestClient(app)
    token_a = _mint_token(client)
    token_b = _mint_token(client)
    assert token_a != token_b
    header_a = {"Authorization": f"Bearer {token_a}"}
    header_b = {"Authorization": f"Bearer {token_b}"}

    # Both tokens authenticate the same single user.
    assert client.get("/api/v1/me", headers=header_a).status_code == 200
    assert client.get("/api/v1/me", headers=header_b).status_code == 200
    with Session(db_engine) as session:  # type: ignore[arg-type]
        assert len(session.exec(select(User)).all()) == 1
        assert len(session.exec(select(AuthSession)).all()) == 2

    # Logout with token_a returns 204 and drops only its row.
    out = client.post("/api/v1/auth/logout", headers=header_a)
    assert out.status_code == 204, out.text
    assert out.content == b""

    with Session(db_engine) as session:  # type: ignore[arg-type]
        rows = session.exec(select(AuthSession)).all()
        assert len(rows) == 1
        assert rows[0].token_hash == hash_session_token(token_b)

    # token_a is dead; token_b still lives.
    assert client.get("/api/v1/me", headers=header_a).status_code == 401
    assert client.get("/api/v1/me", headers=header_b).status_code == 200


def test_expired_session_rejected(
    db_engine: object,
    github_mock: httpx.MockTransport,
) -> None:
    client = TestClient(app)
    token = _mint_token(client)
    header = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/me", headers=header).status_code == 200

    # Backdate the session expiry past now.
    with Session(db_engine) as session:  # type: ignore[arg-type]
        row = session.exec(
            select(AuthSession).where(
                AuthSession.token_hash == hash_session_token(token)
            )
        ).first()
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.add(row)
        session.commit()

    resp = client.get("/api/v1/me", headers=header)
    assert resp.status_code == 401
    assert resp.json()["detail"] == "session expired"


def test_logout_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 401
