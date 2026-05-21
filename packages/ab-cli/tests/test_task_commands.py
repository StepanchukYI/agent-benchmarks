"""Tests for `ab task` subcommands: validate, dry-run, list."""

from __future__ import annotations

import pytest
from ab_cli.main import app
from typer.testing import CliRunner

L0_DIR = "packages/ab-datasets/ab_datasets/L0_foundation"
L0_001_PATH = f"{L0_DIR}/L0_001-create-file-with-content.yaml"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_validate_single_file(runner: CliRunner) -> None:
    result = runner.invoke(app, ["task", "validate", L0_001_PATH])
    assert result.exit_code == 0, result.output
    assert "L0_001" in result.output
    assert "valid" in result.output.lower()


def test_validate_directory_reports_all_l0(runner: CliRunner) -> None:
    # L0 backlog grows toward 20 tasks (build spec §2). This test fixes the
    # lower bound at the original 5 smoke ids and asserts every present
    # file is valid — it must not regress and must keep up with growth.
    result = runner.invoke(app, ["task", "validate", L0_DIR])
    assert result.exit_code == 0, result.output
    for tid in ("L0_001", "L0_002", "L0_003", "L0_004", "L0_005"):
        assert tid in result.output
    import re
    m = re.search(r"summary: (\d+) valid, (\d+) failed \(total (\d+)\)", result.output)
    assert m is not None, result.output
    valid, failed, total = (int(g) for g in m.groups())
    assert failed == 0, result.output
    assert valid == total
    assert valid >= 5, f"expected ≥5 L0 tasks, got {valid}"


def test_dry_run_finds_task(runner: CliRunner) -> None:
    result = runner.invoke(app, ["task", "dry-run", "L0_001"])
    assert result.exit_code == 0, result.output
    assert "L0_001" in result.output


def test_dry_run_unknown_id_exits_one(runner: CliRunner) -> None:
    result = runner.invoke(app, ["task", "dry-run", "L9_999"])
    assert result.exit_code == 1


def test_list_contains_all_five(runner: CliRunner) -> None:
    result = runner.invoke(app, ["task", "list"])
    assert result.exit_code == 0, result.output
    for tid in ("L0_001", "L0_002", "L0_003", "L0_004", "L0_005"):
        assert tid in result.output
