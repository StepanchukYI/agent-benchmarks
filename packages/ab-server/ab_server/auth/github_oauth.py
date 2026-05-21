from __future__ import annotations

import hashlib
import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlmodel import Session, select

from ab_server.config import Settings
from ab_server.models import User


def hash_session_token(token: str) -> str:
    """One-way fingerprint stored in the DB; raw token returned to client only at mint."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

_DEVICE_CODE_PATH = "/login/device/code"
_ACCESS_TOKEN_PATH = "/login/oauth/access_token"
_USER_PATH = "/user"

# Per-process singleton httpx client, guarded by _LOCK.
#
# Scope: this lock guards concurrency WITHIN one process. Under gunicorn -w N
# the workers are forked, each with its own _GH_CLIENT = None — that's fine,
# every worker independently owns its httpx.Client. Inside a single worker,
# FastAPI may dispatch multiple in-flight requests on the asyncio loop (and,
# under starlette's threadpool, multiple OS threads) that all hit the lazy
# initializer. Without the lock, two concurrent callers can both see None,
# both construct a Client, and one of those Clients leaks (no .close()).
# The double-checked-locking pattern below is CPython-safe because the GIL
# orders the inner None-check vs the assignment.
_GH_CLIENT: httpx.Client | None = None
_LOCK = threading.Lock()


def set_github_client(client: httpx.Client) -> None:
    global _GH_CLIENT
    with _LOCK:
        _GH_CLIENT = client


def reset_github_client() -> None:
    global _GH_CLIENT
    with _LOCK:
        if _GH_CLIENT is not None:
            _GH_CLIENT.close()
        _GH_CLIENT = None


def get_github_client() -> httpx.Client:
    global _GH_CLIENT
    # Fast path: already initialised, no lock required.
    if _GH_CLIENT is None:
        with _LOCK:
            # Re-check inside the lock — another thread may have raced ahead.
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
    # GitHub returns 200 + {"error": "..."} for app-config errors like
    # `device_flow_disabled` (OAuth app missing the Device Flow toggle).
    # Some failure modes also surface as 4xx with the same error shape.
    # Either way: surface a useful message instead of letting a generic
    # raise_for_status() bubble up as 500.
    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        return {}
    if isinstance(payload, dict) and "error" in payload:
        from fastapi import HTTPException, status as http_status

        err = payload.get("error", "unknown_error")
        desc = payload.get("error_description") or "GitHub OAuth app rejected the device-flow request."
        # device_flow_disabled is the maintainer's config issue, not the
        # caller's: 503 communicates "service misconfigured", and FE can
        # render the description verbatim.
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"GitHub OAuth: {err} — {desc}",
        )
    response.raise_for_status()
    return payload


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
    user.session_token = hash_session_token(token)
    user.session_expires_at = expires_at
    session.add(user)
    session.commit()
    session.refresh(user)
    return token, expires_at
