from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ApiToken(SQLModel, table=True):
    """User-minted API token for `ab publish` from CI.

    Only the sha256 hash of the plaintext token is stored; the plaintext is
    returned exactly once at mint and never persisted.
    """

    __tablename__ = "api_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str
    token_hash: str = Field(index=True, unique=True)
    prefix: str
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
