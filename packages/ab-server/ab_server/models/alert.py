from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AlertRule(SQLModel, table=True):
    __tablename__ = "alert_rules"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", index=True)
    name: str
    metric: str = "score_total"
    suite: str | None = Field(default=None, nullable=True)
    model: str | None = Field(default=None, nullable=True)
    tier: str | None = Field(default=None, nullable=True)
    direction: str = "down"
    threshold_pct: float = 5.0
    window_days: int = 7
    channels: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    enabled: bool = True
    last_fired_at: datetime | None = Field(default=None, nullable=True)
    last_evaluated_at: datetime | None = Field(default=None, nullable=True)
    created_at: datetime = Field(default_factory=_utcnow)

    def derive_state(self, *, now: datetime | None = None) -> str:
        if self.last_fired_at is None:
            return "idle"
        now = now or datetime.now(UTC)
        last = self.last_fired_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        delta_days = (now - last).total_seconds() / 86400.0
        if delta_days <= float(self.window_days):
            return "firing"
        return "idle"

    def to_dict(self, *, now: datetime | None = None) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "metric": self.metric,
            "suite": self.suite,
            "model": self.model,
            "tier": self.tier,
            "direction": self.direction,
            "threshold_pct": self.threshold_pct,
            "window_days": self.window_days,
            "channels": list(self.channels or []),
            "enabled": self.enabled,
            "last_fired_at": self.last_fired_at.isoformat() if self.last_fired_at else None,
            "last_evaluated_at": (
                self.last_evaluated_at.isoformat() if self.last_evaluated_at else None
            ),
            "created_at": self.created_at.isoformat(),
            "state": self.derive_state(now=now),
        }
