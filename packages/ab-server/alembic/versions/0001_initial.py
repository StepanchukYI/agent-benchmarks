"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-21

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("github_id", sa.String(), nullable=False),
        sa.Column("handle", sa.String(), nullable=False),
        sa.Column("avatar_url", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("github_id", name="uq_users_github_id"),
    )
    op.create_index("ix_users_github_id", "users", ["github_id"], unique=True)

    op.create_table(
        "registered_repos",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("repo_url", sa.String(), nullable=False),
        sa.Column("default_branch", sa.String(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("sync_cursor", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("user_id", "repo_url", name="uq_registered_repos_user_url"),
    )
    op.create_index("ix_registered_repos_user_id", "registered_repos", ["user_id"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("suite", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("tier_hash", sa.String(), nullable=False),
        sa.Column("dataset_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("cost_total_usd", sa.Float(), nullable=False),
    )
    op.create_index("ix_runs_tenant_id", "runs", ["tenant_id"])

    op.create_table(
        "submissions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "registered_repo_id",
            sa.String(length=36),
            sa.ForeignKey("registered_repos.id"),
            nullable=False,
        ),
        sa.Column("source_commit_sha", sa.String(), nullable=False),
        sa.Column("source_path", sa.String(), nullable=False),
        sa.Column("trust_tier", sa.String(), nullable=False),
        sa.Column("re_scored_at", sa.DateTime(), nullable=True),
        sa.Column("discrepancy_pct", sa.Float(), nullable=True),
        sa.Column("ingested_at", sa.DateTime(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("dataset_version", sa.String(), nullable=False),
    )
    op.create_index("ix_submissions_registered_repo_id", "submissions", ["registered_repo_id"])
    op.create_index(
        "ix_submissions_repo_commit",
        "submissions",
        ["registered_repo_id", "source_commit_sha"],
    )

    op.create_table(
        "task_results",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), sa.ForeignKey("runs.id"), nullable=True),
        sa.Column(
            "submission_id",
            sa.String(length=36),
            sa.ForeignKey("submissions.id"),
            nullable=True,
        ),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("suite", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("tier_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("score_correctness", sa.Float(), nullable=False),
        sa.Column("score_context_eff", sa.Float(), nullable=False),
        sa.Column("score_tool_skill", sa.Float(), nullable=False),
        sa.Column("score_memory", sa.Float(), nullable=False),
        sa.Column("score_latency", sa.Float(), nullable=False),
        sa.Column("score_total", sa.Float(), nullable=False),
        sa.Column("cost_usd", sa.Float(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("trajectory_blob_ref", sa.String(), nullable=False),
    )
    op.create_index("ix_task_results_run_id", "task_results", ["run_id"])
    op.create_index("ix_task_results_submission_id", "task_results", ["submission_id"])
    op.create_index(
        "ix_task_results_model_tier_suite",
        "task_results",
        ["model", "tier", "suite"],
    )

    op.create_table(
        "scorer_verdicts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "task_result_id",
            sa.String(length=36),
            sa.ForeignKey("task_results.id"),
            nullable=False,
        ),
        sa.Column("scorer_name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("pass", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
    )
    op.create_index("ix_scorer_verdicts_task_result_id", "scorer_verdicts", ["task_result_id"])

    op.create_table(
        "tiers",
        sa.Column("name", sa.String(), primary_key=True),
        sa.Column("manifest_yaml", sa.Text(), nullable=False),
        sa.Column("total_sha256", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.UniqueConstraint("total_sha256", name="uq_tiers_total_sha256"),
    )
    op.create_index("ix_tiers_total_sha256", "tiers", ["total_sha256"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tiers_total_sha256", table_name="tiers")
    op.drop_table("tiers")

    op.drop_index("ix_scorer_verdicts_task_result_id", table_name="scorer_verdicts")
    op.drop_table("scorer_verdicts")

    op.drop_index("ix_task_results_model_tier_suite", table_name="task_results")
    op.drop_index("ix_task_results_submission_id", table_name="task_results")
    op.drop_index("ix_task_results_run_id", table_name="task_results")
    op.drop_table("task_results")

    op.drop_index("ix_submissions_repo_commit", table_name="submissions")
    op.drop_index("ix_submissions_registered_repo_id", table_name="submissions")
    op.drop_table("submissions")

    op.drop_index("ix_runs_tenant_id", table_name="runs")
    op.drop_table("runs")

    op.drop_index("ix_registered_repos_user_id", table_name="registered_repos")
    op.drop_table("registered_repos")

    op.drop_index("ix_users_github_id", table_name="users")
    op.drop_table("users")
