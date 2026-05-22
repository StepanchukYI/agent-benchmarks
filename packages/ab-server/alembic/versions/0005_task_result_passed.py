"""add passed column to task_results

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-22 00:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("task_results", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("passed", sa.Boolean(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("task_results", schema=None) as batch_op:
        batch_op.drop_column("passed")
