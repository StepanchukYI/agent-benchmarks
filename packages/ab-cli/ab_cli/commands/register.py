"""`ab register` — register a results repo with the leaderboard server."""

from __future__ import annotations

import typer

from ..ui import not_implemented


def register(
    repo_url: str = typer.Argument(..., help="HTTPS URL of the results repository."),
    default_branch: str = typer.Option("main", help="Default branch the server will pull from."),
) -> None:
    """Register a results repo (GitHub OAuth device flow)."""
    not_implemented(
        "register",
        reason=(
            f"would register {repo_url} (branch={default_branch}) — "
            "Phase 1 row 7 (GitHub OAuth device flow + repo registration)"
        ),
    )
