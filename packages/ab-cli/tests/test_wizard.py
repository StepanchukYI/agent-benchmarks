"""`ab wizard --dry` walks numbered prompts and prints the `ab run` invocation.

Smoke: pipe a sequence of "1\\n" defaults → confirm the printed invocation
has the expected flags. No subprocess actually runs in --dry mode.
"""

from __future__ import annotations

import re

from ab_cli.main import app
from typer.testing import CliRunner

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", _ANSI_RE.sub("", text))


def test_wizard_dry_run_prints_invocation() -> None:
    runner = CliRunner()
    # Inputs:
    #   1) Runner pick           → 1 = claude-code
    #   2) Model pick            → 1 = first model in models_for_runner
    #   3) Effort pick           → 2 = medium (default_idx=1)
    #   4) Vendor pick           → 1 = anthropic
    #   5) Suite pick            → 1 = L0_smoke
    #   6) Tier pick             → 1 = T0
    #   7) Single task id        → blank
    stdin = "1\n1\n2\n1\n1\n1\n\n"
    result = runner.invoke(app, ["wizard", "--dry"], input=stdin)
    assert result.exit_code == 0, result.output
    out = _strip(result.output)
    assert "ab run --suite L0_smoke" in out
    assert "--runner claude-code" in out
    assert "--tier T0" in out
    assert "--effort medium" in out
    # vendor default is index 0 = "anthropic"
    assert "--vendor anthropic" in out


def test_wizard_skips_effort_for_mock_runner() -> None:
    runner = CliRunner()
    # mock is the LAST option in the runner list.
    # PRIORITY_SCAFFOLDS_V1 has 4 entries (claude-code/codex-cli/gemini-cli/opencode)
    # + pi-agent in our wizard hardcoded list? Actually wizard.py builds the
    # runner list as PRIORITY + anthropic-compat + openai-compat + local + mock.
    # PRIORITY_SCAFFOLDS_V1 = ('claude-code', 'codex-cli', 'gemini-cli',
    # 'opencode'). pi-agent is appended via the same priority tuple? Check.
    from ab_harness.models import PRIORITY_SCAFFOLDS_V1

    extras = ["anthropic-compat", "openai-compat", "local", "mock"]
    runner_list = [*PRIORITY_SCAFFOLDS_V1, *extras]
    mock_idx = runner_list.index("mock") + 1
    # Pick mock → skip effort → no vendor (only claude-code asks for it) →
    # suite 1 → tier 1 → blank task.
    stdin = f"{mock_idx}\n1\n1\n1\n\n"
    result = runner.invoke(app, ["wizard", "--dry"], input=stdin)
    assert result.exit_code == 0, result.output
    out = _strip(result.output)
    assert "--runner mock" in out
    assert "--effort" not in out
    assert "--vendor" not in out
