"""Typer entry point for the `ab` CLI."""

from __future__ import annotations

import typer

from . import __version__
from .commands.evolve import evolve
from .commands.publish import publish
from .commands.register import register
from .commands.replay import replay
from .commands.run import run
from .commands.submit import submit
from .ui import console

app = typer.Typer(
    name="ab",
    help=(
        "agent-benchmarks operator CLI. Register a results repo, run a suite "
        "against a model, publish results, replay or submit a run, and evolve "
        "the L5 task set."
    ),
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"ab {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Print the ab-cli version and exit.",
        is_eager=True,
        callback=_version_callback,
    ),
) -> None:
    """Top-level options for the ab CLI."""


app.command("register", help="Register a results repository with the leaderboard server.")(register)
app.command("run", help="Run a benchmark suite against a model.")(run)
app.command("publish", help="Commit and push results to the registered repo.")(publish)
app.command("replay", help="Replay a remote commit on a fresh runner.")(replay)
app.command("submit", help="Self-report a submission (legacy push, ADR-007 fallback).")(submit)
app.command("evolve", help="Run a generation of the L5 auto-evolution loop.")(evolve)


if __name__ == "__main__":
    app()
