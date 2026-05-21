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


def test_register_stub_prints_not_implemented(runner: CliRunner) -> None:
    result = runner.invoke(app, ["register", "https://example.com/foo"])
    assert result.exit_code == 0
    assert "not implemented" in result.output.lower()
