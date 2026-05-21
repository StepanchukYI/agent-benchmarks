from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlmodel import Session, select

from ab_server.config import Settings
from ab_server.db import get_session
from ab_server.models import User


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth:
        return None
    parts = auth.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def get_current_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    x_test_user: Annotated[str | None, Header(alias="X-Test-User")] = None,
) -> User:
    settings = Settings()

    if settings.ab_test_auth and x_test_user:
        return _ensure_test_user(session, x_test_user)

    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    user = session.exec(select(User).where(User.session_token == token)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    if user.session_expires_at is not None:
        expires = user.session_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired"
            )
    return user


def _ensure_test_user(session: Session, handle: str) -> User:
    gh_id = f"test:{handle}"
    user = session.exec(select(User).where(User.github_id == gh_id)).first()
    if user is None:
        user = User(github_id=gh_id, handle=handle, avatar_url=None)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
