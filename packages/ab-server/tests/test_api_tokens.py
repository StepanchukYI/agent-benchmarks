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
    db_path = tmp_path / "tokens.db"
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


def test_list_tokens_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/account/tokens")
    assert resp.status_code == 401


def test_create_token_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post("/api/v1/account/tokens", json={"name": "ci"})
    assert resp.status_code == 401


def test_delete_token_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.delete("/api/v1/account/tokens/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 401


def test_list_tokens_empty(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/account/tokens", headers=_h("alice"))
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_returns_plaintext_once(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/account/tokens",
        json={"name": "ci-publish"},
        headers=_h("alice"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "ci-publish"
    assert "token" in body
    plaintext = body["token"]
    assert isinstance(plaintext, str) and len(plaintext) >= 32
    assert body["prefix"] == plaintext[:8]
    assert "id" in body

    # Listing must not include the plaintext anywhere.
    listed = client.get("/api/v1/account/tokens", headers=_h("alice"))
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    item = items[0]
    assert item["id"] == body["id"]
    assert item["name"] == "ci-publish"
    assert item["prefix"] == plaintext[:8]
    assert item["revoked"] is False
    assert item["last_used_at"] is None
    assert "token" not in item
    # Ensure plaintext does not leak in any field.
    for v in item.values():
        if isinstance(v, str):
            assert plaintext not in v


def test_delete_token_returns_204_and_marks_revoked(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/account/tokens",
        json={"name": "to-revoke"},
        headers=_h("alice"),
    )
    assert created.status_code == 201
    token_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/account/tokens/{token_id}", headers=_h("alice")
    )
    assert deleted.status_code == 204
    assert deleted.content in (b"", b"null")

    # After delete the token should be marked revoked in the listing.
    listed = client.get("/api/v1/account/tokens", headers=_h("alice"))
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 1
    assert items[0]["id"] == token_id
    assert items[0]["revoked"] is True
    assert items[0]["revoked_at"] is not None


def test_tokens_isolated_per_user(db_engine: object) -> None:
    client = TestClient(app)
    client.post(
        "/api/v1/account/tokens",
        json={"name": "alice-ci"},
        headers=_h("alice"),
    )
    bob_list = client.get("/api/v1/account/tokens", headers=_h("bob"))
    assert bob_list.status_code == 200
    assert bob_list.json() == []


def test_delete_other_users_token_returns_404(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/account/tokens",
        json={"name": "alice-ci"},
        headers=_h("alice"),
    )
    assert created.status_code == 201
    token_id = created.json()["id"]

    resp = client.delete(
        f"/api/v1/account/tokens/{token_id}", headers=_h("bob")
    )
    assert resp.status_code == 404


def test_create_empty_name_rejected(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/account/tokens",
        json={"name": "   "},
        headers=_h("alice"),
    )
    assert resp.status_code == 400


def test_minted_token_authenticates(db_engine: object) -> None:
    """A minted API token must authenticate via Authorization: Bearer.

    Regression for the audit finding: get_current_user only checked
    User.session_token and never consulted ApiToken.token_hash, so every
    token from POST /account/tokens was dead on arrival.
    """
    client = TestClient(app)
    created = client.post(
        "/api/v1/account/tokens",
        json={"name": "ci-publish"},
        headers=_h("alice"),
    )
    assert created.status_code == 201, created.text
    plaintext = created.json()["token"]

    # Use ONLY the Bearer token (no X-Test-User), so the real token path
    # in get_current_user is exercised even with AB_TEST_AUTH=1.
    resp = client.get(
        "/api/v1/account/tokens",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert resp.status_code == 200, (
        f"minted API token must authenticate, got {resp.status_code}: {resp.text}"
    )
    # last_used_at should now be set on the token row.
    item = resp.json()[0]
    assert item["last_used_at"] is not None


def test_revoked_token_rejected(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/account/tokens",
        json={"name": "ci-temp"},
        headers=_h("alice"),
    )
    plaintext = created.json()["token"]
    token_id = created.json()["id"]
    # Revoke it.
    client.delete(f"/api/v1/account/tokens/{token_id}", headers=_h("alice"))
    # Now the bearer must be rejected.
    resp = client.get(
        "/api/v1/account/tokens",
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert resp.status_code == 401, (
        f"revoked token must 401, got {resp.status_code}"
    )
