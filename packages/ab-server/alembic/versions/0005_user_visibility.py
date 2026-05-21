"""user visibility columns (public_profile, share_runs)

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", recreate="auto") as batch:
        batch.add_column(
            sa.Column(
                "public_profile",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch.add_column(
            sa.Column(
                "share_runs",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", recreate="auto") as batch:
        batch.drop_column("share_runs")
        batch.drop_column("public_profile")
