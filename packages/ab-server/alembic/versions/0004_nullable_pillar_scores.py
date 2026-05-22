"""make per-pillar score columns nullable (null = pillar not measured)

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-22 00:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PILLAR_COLUMNS = (
    "score_correctness",
    "score_context_eff",
    "score_tool_skill",
    "score_memory",
    "score_latency",
)


def upgrade() -> None:
    with op.batch_alter_table("task_results", schema=None) as batch_op:
        for col in _PILLAR_COLUMNS:
            batch_op.alter_column(
                col,
                existing_type=sa.Float(),
                nullable=True,
                existing_server_default=None,
            )


def downgrade() -> None:
    # Revert to NOT NULL; backfill any NULLs to 0.0 first so the constraint holds.
    for col in _PILLAR_COLUMNS:
        op.execute(f"UPDATE task_results SET {col} = 0.0 WHERE {col} IS NULL")
    with op.batch_alter_table("task_results", schema=None) as batch_op:
        for col in _PILLAR_COLUMNS:
            batch_op.alter_column(
                col,
                existing_type=sa.Float(),
                nullable=False,
                server_default="0.0",
            )
