"""submissions: unique (registered_repo_id, source_commit_sha, source_path)

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-21

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("submissions", recreate="auto") as batch:
        batch.create_unique_constraint(
            "uq_submissions_repo_commit_path",
            ["registered_repo_id", "source_commit_sha", "source_path"],
        )


def downgrade() -> None:
    with op.batch_alter_table("submissions", recreate="auto") as batch:
        batch.drop_constraint("uq_submissions_repo_commit_path", type_="unique")
