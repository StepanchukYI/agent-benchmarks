"""api_tokens table

Revision ID: 0006
Revises: 0005, afde30329b5c
Create Date: 2026-05-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
# Merge the two existing heads (0005_user_visibility and afde30329b5c_add_fetch_jobs_table)
# into one linear chain before adding the api_tokens table.
down_revision: str | tuple[str, ...] | None = ("0005", "afde30329b5c")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column("prefix", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_api_tokens_user_id"),
            ["user_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_api_tokens_token_hash"),
            ["token_hash"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_api_tokens_token_hash"))
        batch_op.drop_index(batch_op.f("ix_api_tokens_user_id"))
    op.drop_table("api_tokens")
