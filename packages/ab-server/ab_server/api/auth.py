from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlmodel import Session

from ab_server.auth.dependency import get_current_user
from ab_server.auth.github_oauth import device_poll, device_start
from ab_server.config import Settings
from ab_server.db import get_session
from ab_server.models import User

router = APIRouter(tags=["auth"])


class _ClientIdResponse(BaseModel):
    client_id: str


class _DeviceStartRequest(BaseModel):
    client_id: str | None = None


class _DevicePollRequest(BaseModel):
    client_id: str | None = None
    device_code: str


class _VisibilityUpdate(BaseModel):
    public_profile: bool | None = None
    share_runs: bool | None = None


def _user_out(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "github_id": user.github_id,
        "handle": user.handle,
        "avatar_url": user.avatar_url,
        "public_profile": user.public_profile,
        "share_runs": user.share_runs,
    }


@router.get("/auth/github/client-id", response_model=_ClientIdResponse)
def github_client_id() -> _ClientIdResponse:
    return _ClientIdResponse(client_id=Settings().github_client_id)


@router.post("/auth/github/device-start")
def github_device_start(
    payload: Annotated[_DeviceStartRequest, Body(...)],
) -> dict[str, Any]:
    settings = Settings()
    client_id = payload.client_id or settings.github_client_id
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_id not configured",
        )
    return device_start(client_id)


@router.post("/auth/github/device-poll")
def github_device_poll(
    payload: Annotated[_DevicePollRequest, Body(...)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    settings = Settings()
    client_id = payload.client_id or settings.github_client_id
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_id not configured",
        )
    return device_poll(session, client_id=client_id, device_code=payload.device_code)


# Kept for OpenAPI parity with Build Spec §10; future-deprecated by device flow.
@router.get("/auth/github/login")
def github_login() -> dict[str, str]:
    return {"detail": "use POST /auth/github/device-start (device flow)"}


@router.get("/auth/github/callback")
def github_callback() -> dict[str, str]:
    return {"detail": "device flow does not use a browser callback"}


@router.get("/me")
def me(user: Annotated[User, Depends(get_current_user)]) -> dict[str, Any]:
    return _user_out(user)


@router.patch("/me/visibility")
def update_me_visibility(
    payload: Annotated[_VisibilityUpdate, Body(...)],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    """Partial update of visibility toggles for the current user.

    Body fields are all optional; only provided fields are applied.
    """
    if payload.public_profile is not None:
        user.public_profile = payload.public_profile
    if payload.share_runs is not None:
        user.share_runs = payload.share_runs
    session.add(user)
    session.commit()
    session.refresh(user)
    return _user_out(user)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Invalidate the caller's session token.

    Clears the hashed session_token (and its expiry) on the user row so the
    bearer token can no longer authenticate. Subsequent requests with the
    same token will 401 in get_current_user.
    """
    user.session_token = None
    user.session_expires_at = None
    session.add(user)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
