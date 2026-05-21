from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlmodel import Session, select

from ab_server.config import Settings
from ab_server.models import User

_DEVICE_CODE_PATH = "/login/device/code"
_ACCESS_TOKEN_PATH = "/login/oauth/access_token"
_USER_PATH = "/user"

_GH_CLIENT: httpx.Client | None = None


def set_github_client(client: httpx.Client) -> None:
    global _GH_CLIENT
    _GH_CLIENT = client


def reset_github_client() -> None:
    global _GH_CLIENT
    if _GH_CLIENT is not None:
        _GH_CLIENT.close()
    _GH_CLIENT = None


def get_github_client() -> httpx.Client:
    global _GH_CLIENT
    if _GH_CLIENT is None:
        _GH_CLIENT = httpx.Client(timeout=15.0)
    return _GH_CLIENT


def device_start(client_id: str) -> dict[str, Any]:
    settings = Settings()
    url = f"{settings.github_device_base}{_DEVICE_CODE_PATH}"
    response = get_github_client().post(
        url,
        data={"client_id": client_id, "scope": "read:user"},
        headers={"Accept": "application/json"},
    )
    response.raise_for_status()
    return response.json()


def device_poll(
    session: Session,
    *,
    client_id: str,
    device_code: str,
) -> dict[str, Any]:
    settings = Settings()
    token_url = f"{settings.github_device_base}{_ACCESS_TOKEN_PATH}"
    token_resp = get_github_client().post(
        token_url,
        data={
            "client_id": client_id,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
        headers={"Accept": "application/json"},
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()
    if "error" in token_data:
        return token_data
    access_token = token_data.get("access_token")
    if not access_token:
        return token_data

    user_url = f"{settings.github_api_base}{_USER_PATH}"
    user_resp = get_github_client().get(
        user_url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
        },
    )
    user_resp.raise_for_status()
    profile = user_resp.json()

    user = _upsert_user(session, profile)
    session_token, expires_at = _mint_session(session, user, ttl_seconds=settings.session_ttl_seconds)

    return {
        "access_token": session_token,
        "github_login": user.handle,
        "expires_at": expires_at.isoformat(),
    }


def _upsert_user(session: Session, profile: dict[str, Any]) -> User:
    gh_id = str(profile.get("id"))
    handle = str(profile.get("login") or profile.get("name") or "unknown")
    avatar = profile.get("avatar_url")
    user = session.exec(select(User).where(User.github_id == gh_id)).first()
    if user is None:
        user = User(github_id=gh_id, handle=handle, avatar_url=avatar)
        session.add(user)
    else:
        user.handle = handle
        user.avatar_url = avatar
        session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _mint_session(
    session: Session,
    user: User,
    *,
    ttl_seconds: int,
) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    user.session_token = token
    user.session_expires_at = expires_at
    session.add(user)
    session.commit()
    session.refresh(user)
    return token, expires_at
