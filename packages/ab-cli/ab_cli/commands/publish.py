"""`ab publish` — git add/commit/push wrapper for results repos."""

from __future__ import annotations

import typer

from ..ui import not_implemented


def publish(
    message: str = typer.Option("update results", help="Commit message."),
) -> None:
    """Commit and push the local results dir to the registered repo."""
    not_implemented(
        "publish",
        reason=(
            f"would git add/commit/push (message={message!r}) — "
            "Phase 1 row 7 (ab publish git wrapper)"
        ),
    )
