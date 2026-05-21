"""Render a short markdown summary from a Trajectory."""

from __future__ import annotations

from typing import Any


def render_run(trajectory: Any) -> str:
    run_id = getattr(trajectory, "run_id", "?")
    model = getattr(trajectory, "model", "?")
    harness = getattr(trajectory, "harness", "?")
    tier = getattr(trajectory, "tier", "?")
    turns = getattr(trajectory, "turns", []) or []
    totals = getattr(trajectory, "totals", None)

    lines = [
        f"# Run `{run_id}`",
        "",
        f"- model: `{model}`",
        f"- harness: `{harness}`",
        f"- tier: `{tier}`",
        f"- turns: {len(turns)}",
    ]
    if totals is not None:
        lines.append(f"- totals: `{totals}`")
    return "\n".join(lines) + "\n"
