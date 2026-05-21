from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from ab_server.auth.dependency import get_current_user
from ab_server.db import get_session
from ab_server.models import ApiToken, User

router = APIRouter(tags=["account"])


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


class ApiTokenOut(BaseModel):
    id: str
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None
    revoked: bool = False
    revoked_at: datetime | None = None


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ApiTokenCreated(BaseModel):
    id: str
    name: str
    prefix: str
    token: str  # one-time plaintext; never returned again


def _to_out(row: ApiToken) -> ApiTokenOut:
    return ApiTokenOut(
        id=str(row.id),
        name=row.name,
        prefix=row.prefix,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked=row.revoked_at is not None,
        revoked_at=row.revoked_at,
    )


@router.get("/account/tokens", response_model=list[ApiTokenOut])
def list_account_tokens(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[ApiTokenOut]:
    rows = session.exec(
        select(ApiToken)
        .where(ApiToken.user_id == user.id)
        .order_by(ApiToken.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [_to_out(r) for r in rows]


@router.post(
    "/account/tokens",
    response_model=ApiTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_account_token(
    payload: ApiTokenCreate,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ApiTokenCreated:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    plaintext = secrets.token_urlsafe(32)
    token_hash = _hash_token(plaintext)
    # Display prefix (first 8 chars of plaintext) — safe to store, helps the
    # user identify the token in lists without leaking secret material.
    prefix = plaintext[:8]

    row = ApiToken(
        user_id=user.id,
        name=name,
        token_hash=token_hash,
        prefix=prefix,
    )
    session.add(row)
    session.commit()
    session.refresh(row)

    return ApiTokenCreated(
        id=str(row.id),
        name=row.name,
        prefix=row.prefix,
        token=plaintext,
    )


@router.delete(
    "/account/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_account_token(
    token_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    row = session.exec(
        select(ApiToken)
        .where(ApiToken.id == token_id)
        .where(ApiToken.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="token not found")
    if row.revoked_at is None:
        from datetime import UTC
        from datetime import datetime as _dt

        row.revoked_at = _dt.now(UTC)
        session.add(row)
        session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
