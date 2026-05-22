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
    # Per-pillar scores: None means the pillar was NOT measured for this task
    # (its scorer was absent from the task's chain), distinct from a genuine
    # measured 0.0. The leaderboard treats None as "no data" and a real 0.0 as
    # data — so a count-based aggregate never hides a true zero.
    score_correctness: float | None = None
    score_context_eff: float | None = None
    score_tool_skill: float | None = None
    score_memory: float | None = None
    score_latency: float | None = None
    score_total: float = 0.0
    cost_usd: float = 0.0
    latency_ms: int = 0
    tokens_total: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    turns_total: int = 0
    trajectory_blob_ref: str = ""
