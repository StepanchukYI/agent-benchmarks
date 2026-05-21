from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class ScorerVerdictRow(SQLModel, table=True):
    __tablename__ = "scorer_verdicts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    task_result_id: UUID = Field(foreign_key="task_results.id", index=True)
    scorer_name: str
    kind: str
    pass_: bool = Field(sa_column=sa.Column("pass", sa.Boolean, nullable=False))
    score: float = 0.0
    detail: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=sa.Column(sa.JSON, nullable=False),
    )
