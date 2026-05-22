from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    github_id: str = Field(index=True, unique=True)
    handle: str
    avatar_url: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    public_profile: bool = Field(default=True)
    share_runs: bool = Field(default=True)
