from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import Index
from sqlmodel import Field, SQLModel


class TaskResult(SQLModel, table=True):
    __tablename__ = "task_results"
    __table_args__ = (
        Index("ix_task_results_model_tier_suite", "model", "tier", "suite"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    run_id: UUID | None = Field(default=None, foreign_key="runs.id", index=True)
    submission_id: UUID | None = Field(default=None, foreign_key="submissions.id", index=True)
    task_id: str
    suite: str
    model: str
    tier: str
    tier_hash: str
    status: str = "pending"
    score_correctness: float = 0.0
    score_context_eff: float = 0.0
    score_tool_skill: float = 0.0
    score_memory: float = 0.0
    score_latency: float = 0.0
    score_total: float = 0.0
    cost_usd: float = 0.0
    latency_ms: int = 0
    trajectory_blob_ref: str = ""
