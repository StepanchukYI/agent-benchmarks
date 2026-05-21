from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class RunPreset(SQLModel, table=True):
    __tablename__ = "run_presets"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_run_presets_user_name"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str
    suites: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    task_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    models: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    tier: str = "T0"
    repetitions: int = 1
    sandbox: str = "local"
    concurrency: int = 1
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    # Convenience accessor; tests/serializers can use this without caring about
    # the underlying sa_column behavior.
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "suites": list(self.suites or []),
            "task_ids": list(self.task_ids or []),
            "models": list(self.models or []),
            "tier": self.tier,
            "repetitions": self.repetitions,
            "sandbox": self.sandbox,
            "concurrency": self.concurrency,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
