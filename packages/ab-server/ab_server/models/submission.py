from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Submission(SQLModel, table=True):
    __tablename__ = "submissions"
    __table_args__ = (
        Index("ix_submissions_repo_commit", "registered_repo_id", "source_commit_sha"),
        UniqueConstraint(
            "registered_repo_id",
            "source_commit_sha",
            "source_path",
            name="uq_submissions_repo_commit_path",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    registered_repo_id: UUID = Field(foreign_key="registered_repos.id", index=True)
    source_commit_sha: str
    source_path: str
    trust_tier: str = "self_reported"
    re_scored_at: datetime | None = None
    discrepancy_pct: float | None = None
    ingested_at: datetime = Field(default_factory=_utcnow)
    model: str
    tier: str
    dataset_version: str
