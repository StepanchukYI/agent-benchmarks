from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    tenant_id: str = Field(default="self", index=True)
    suite: str
    model: str
    tier: str
    tier_hash: str
    dataset_version: str
    status: str = "pending"
    started_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    cost_total_usd: float = 0.0
    expected_total: int | None = Field(default=None, nullable=True)
    label: str | None = Field(default=None, nullable=True)
