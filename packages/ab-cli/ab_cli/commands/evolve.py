"""`ab evolve` — L5 auto-evolution loop (Phase 7)."""

from __future__ import annotations

import typer

from ..ui import not_implemented


def evolve(
    generation: int = typer.Option(1, help="Evolution generation index."),
) -> None:
    """Run one generation of the auto-evolution loop over evolved tasks."""
    not_implemented(
        "evolve",
        reason=f"L5 auto-evolution loop, Phase 7 (generation={generation})",
    )
