from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthSession(SQLModel, table=True):
    """One bearer session per login, keyed by sha256(token).

    Replaces the single User.session_token column so concurrent logins
    (CLI + web) each get their own row instead of clobbering each other.
    Only the hash is stored; the plaintext token is returned once at mint.
    """

    __tablename__ = "auth_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    origin: str | None = None
