"""`ab run` — execute a benchmark suite against a model."""

from __future__ import annotations

import typer

from ..ui import not_implemented


def run(
    suite: str = typer.Option(..., help="Suite id, e.g. L0_smoke."),
    model: str = typer.Option(..., help="Model id, e.g. claude-sonnet-4-5."),
    tier: str = typer.Option("T0", help="Initial config tier (T0/T1/T2/T3)."),
    tiers: str | None = typer.Option(
        None, help="Comma-separated tiers for cross-tier runs, e.g. T0,T2."
    ),
) -> None:
    """Run a suite against a model at one or more tiers."""
    spec = f"suite={suite} model={model} tier={tier}"
    if tiers:
        spec += f" tiers={tiers}"
    not_implemented(
        "run",
        reason=f"would execute {spec} — Phase 1 row 6 (ab run end-to-end against Claude Code)",
    )
