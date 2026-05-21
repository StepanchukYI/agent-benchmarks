"""CLI smoke tests: --help lists every command; stubs print not-implemented."""

from __future__ import annotations

import pytest
from ab_cli.main import app
from typer.testing import CliRunner

COMMANDS = ["register", "run", "publish", "replay", "submit", "evolve"]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_top_level_help_lists_all_commands(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in COMMANDS:
        assert cmd in result.output


@pytest.mark.parametrize("cmd", COMMANDS)
def test_subcommand_help(runner: CliRunner, cmd: str) -> None:
    result = runner.invoke(app, [cmd, "--help"])
    assert result.exit_code == 0


def test_register_help_lists_options(runner: CliRunner) -> None:
    result = runner.invoke(app, ["register", "--help"])
    assert result.exit_code == 0
    assert "default-branch" in result.output.lower() or "default_branch" in result.output.lower()
    assert "server" in result.output.lower()


def test_publish_help_lists_dry_run(runner: CliRunner) -> None:
    result = runner.invoke(app, ["publish", "--help"])
    assert result.exit_code == 0
    assert "dry-run" in result.output.lower() or "dry_run" in result.output.lower()
