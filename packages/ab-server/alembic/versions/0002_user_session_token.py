"""user session token columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users", recreate="auto") as batch:
        batch.add_column(sa.Column("session_token", sa.String(), nullable=True))
        batch.add_column(sa.Column("session_expires_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_users_session_token",
        "users",
        ["session_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_session_token", table_name="users")
    with op.batch_alter_table("users", recreate="auto") as batch:
        batch.drop_column("session_expires_at")
        batch.drop_column("session_token")
