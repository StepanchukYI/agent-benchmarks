"""add fetch_jobs table

Adds the durable queue row for background `POST /repos/{id}/sync`.

The autogenerate run also surfaced spurious VARCHAR(36) → Uuid alter_column
operations on every existing UUID column. Those are a SQLite vs Postgres
type-representation quirk — on Postgres the columns are already Uuid; on
SQLite both VARCHAR(36) and Uuid hold the same str data. Stripped from
this migration to keep it focused on the new table only.

Revision ID: afde30329b5c
Revises: 0004
Create Date: 2026-05-21 14:39:32.475211+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "afde30329b5c"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fetch_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("repo_id", sa.Uuid(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_after", sa.DateTime(), nullable=True),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("triggered_by", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(
            ["repo_id"],
            ["registered_repos.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("fetch_jobs", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_fetch_jobs_enqueued_at"),
            ["enqueued_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_fetch_jobs_next_attempt_after"),
            ["next_attempt_after"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_fetch_jobs_repo_id"),
            ["repo_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_fetch_jobs_status"),
            ["status"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("fetch_jobs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_fetch_jobs_status"))
        batch_op.drop_index(batch_op.f("ix_fetch_jobs_repo_id"))
        batch_op.drop_index(batch_op.f("ix_fetch_jobs_next_attempt_after"))
        batch_op.drop_index(batch_op.f("ix_fetch_jobs_enqueued_at"))
    op.drop_table("fetch_jobs")
