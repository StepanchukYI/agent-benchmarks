"""Shared Rich helpers for CLI output."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()


def not_implemented(name: str, *, reason: str) -> None:
    """Render a styled panel announcing an unimplemented subcommand."""
    body = Text()
    body.append("not implemented yet\n\n", style="bold yellow")
    body.append(reason, style="white")
    console.print(
        Panel(
            body,
            title=f"ab {name}",
            title_align="left",
            border_style="yellow",
        )
    )
