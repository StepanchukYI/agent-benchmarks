"""`ab submit` — legacy push submission (ADR-007 fallback)."""

from __future__ import annotations

import typer

from ..ui import not_implemented


def submit(
    server: str = typer.Option(
        "https://leaderboard.example.com",
        help="Leaderboard server base URL.",
    ),
) -> None:
    """Self-report a submission via legacy push protocol."""
    not_implemented(
        "submit",
        reason=(
            f"legacy push submission to {server} — kept for P1 fallback; "
            "prefer 'ab register' + 'ab publish' (ADR-007)"
        ),
    )
