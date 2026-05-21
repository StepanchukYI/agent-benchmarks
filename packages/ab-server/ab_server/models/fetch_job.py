"""Background fetcher job — durable queue row for `POST /repos/{id}/sync`.

Replaces the prior in-request sync path. `POST /repos/{id}/sync` enqueues a
FetchJob and returns 202 + job_id; a background poller (started by the FastAPI
lifespan) claims one job per tick and runs the existing `sync_repo` logic
against it.

Status lifecycle:
    queued -> in_progress -> {done | failed | retrying}

A row stays around indefinitely so callers can observe history. Old `done`
rows are not auto-pruned — that's an admin concern, out of scope for v1.

Concurrency: the poller claims a job via UPDATE ... WHERE status='queued'
returning the id, which is portable across SQLite + Postgres without
SELECT...FOR UPDATE. See `claim_next_job` in `ab_server/fetcher/queue.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column
from sqlalchemy.types import JSON
from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FetchJob(SQLModel, table=True):
    __tablename__ = "fetch_jobs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    repo_id: UUID = Field(foreign_key="registered_repos.id", index=True)

    # queued | in_progress | done | failed | retrying
    status: str = Field(default="queued", index=True)
    attempts: int = Field(default=0)
    max_attempts: int = Field(default=3)

    enqueued_at: datetime = Field(default_factory=_utcnow, index=True)
    started_at: datetime | None = Field(default=None, nullable=True)
    finished_at: datetime | None = Field(default=None, nullable=True)
    next_attempt_after: datetime | None = Field(default=None, nullable=True, index=True)

    error: str | None = Field(default=None, nullable=True)
    result: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )

    # Free-text origin tag (e.g. "manual" / "cron" / "alert") so operators
    # can tell where a job came from. Not a foreign key — just a label.
    triggered_by: str = Field(default="manual")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "repo_id": str(self.repo_id),
            "status": self.status,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "enqueued_at": self.enqueued_at.isoformat() if self.enqueued_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "next_attempt_after": (
                self.next_attempt_after.isoformat() if self.next_attempt_after else None
            ),
            "error": self.error,
            "result": self.result,
            "triggered_by": self.triggered_by,
        }
