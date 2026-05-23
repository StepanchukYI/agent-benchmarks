"""add prompt_label to task_results and create prompt_blobs table

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-22 00:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add nullable prompt_label column to task_results (extend-only).
    with op.batch_alter_table("task_results", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("prompt_label", sa.String(), nullable=True)
        )

    # Create content-addressed prompt_blobs table.
    op.create_table(
        "prompt_blobs",
        sa.Column("prompt_hash", sa.String(), primary_key=True),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("prompt_blobs")
    with op.batch_alter_table("task_results", schema=None) as batch_op:
        batch_op.drop_column("prompt_label")
