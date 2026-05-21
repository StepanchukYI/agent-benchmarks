"""Phase 0 cross-package smoke tests.

Verifies that every package exposes the symbols the rest of the system depends on.
"""

from __future__ import annotations


def test_datasets_schemas_importable() -> None:
    from ab_datasets.schemas import Task, Trajectory  # noqa: F401


def test_harness_trajectory_writer_importable() -> None:
    from ab_harness.trajectory import TrajectoryWriter  # noqa: F401


def test_server_app_exposes_leaderboard_route() -> None:
    from ab_server.main import app

    spec = app.openapi()
    paths = spec.get("paths", {})
    assert "/api/v1/leaderboard" in paths, sorted(paths)


def test_sdk_write_run_dir_importable() -> None:
    from ab_sdk import write_run_dir  # noqa: F401


def test_cli_app_importable() -> None:
    from ab_cli.main import app as cli_app  # noqa: F401
