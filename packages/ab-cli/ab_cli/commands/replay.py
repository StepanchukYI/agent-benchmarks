"""`ab replay` — replay a remote commit on a fresh runner."""

from __future__ import annotations

import typer

from ..ui import not_implemented


def replay(
    run_id: str = typer.Argument(..., help="Run id to replay."),
    commit_sha: str = typer.Argument(..., help="Source commit sha to check out before replay."),
) -> None:
    """Replay a recorded trajectory from a published results commit."""
    not_implemented(
        "replay",
        reason=(
            f"would replay run_id={run_id} at commit={commit_sha} — "
            "depends on ab-sdk.replay and the harness runner contract"
        ),
    )
