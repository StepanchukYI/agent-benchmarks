from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RegisteredRepo(SQLModel, table=True):
    __tablename__ = "registered_repos"
    __table_args__ = (UniqueConstraint("user_id", "repo_url", name="uq_registered_repos_user_url"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    repo_url: str
    default_branch: str = "main"
    last_synced_at: datetime | None = None
    sync_cursor: str | None = None
    status: str = "registered"
    is_public: bool = True
    created_at: datetime = Field(default_factory=_utcnow)
