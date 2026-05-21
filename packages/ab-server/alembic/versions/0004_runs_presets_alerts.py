"""runs.expected_total + label, run_presets, alert_rules

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs", recreate="auto") as batch:
        batch.add_column(sa.Column("expected_total", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("label", sa.String(), nullable=True))

    op.create_table(
        "run_presets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("suites", sa.JSON(), nullable=False),
        sa.Column("task_ids", sa.JSON(), nullable=False),
        sa.Column("models", sa.JSON(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("sandbox", sa.String(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_run_presets_user_name"),
    )
    op.create_index("ix_run_presets_user_id", "run_presets", ["user_id"])

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("suite", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("tier", sa.String(), nullable=True),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("threshold_pct", sa.Float(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("channels", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_fired_at", sa.DateTime(), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_alert_rules_user_id", "alert_rules", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_alert_rules_user_id", table_name="alert_rules")
    op.drop_table("alert_rules")

    op.drop_index("ix_run_presets_user_id", table_name="run_presets")
    op.drop_table("run_presets")

    with op.batch_alter_table("runs", recreate="auto") as batch:
        batch.drop_column("label")
        batch.drop_column("expected_total")
