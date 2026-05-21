"""CLI smoke tests: --help lists every command; stubs print not-implemented."""

from __future__ import annotations

import re

import pytest
from ab_cli.main import app
from typer.testing import CliRunner

COMMANDS = ["register", "run", "publish", "replay", "submit", "evolve", "wizard"]

# Strip ANSI escapes (Typer's rich help colorizes when rendered to a real PTY,
# but CI runners with narrower terminals also wrap long option names across
# lines, breaking naive substring checks).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", _ANSI_RE.sub("", text)).lower()


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
    text = _normalize(result.output)
    assert "default-branch" in text or "default_branch" in text or "defaultbranch" in text
    assert "server" in text


def test_publish_help_lists_dry_run(runner: CliRunner) -> None:
    result = runner.invoke(app, ["publish", "--help"])
    assert result.exit_code == 0
    text = _normalize(result.output)
    assert "dry-run" in text or "dry_run" in text or "dryrun" in text
