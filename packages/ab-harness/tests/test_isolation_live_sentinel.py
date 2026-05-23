"""Tier B gated live-sentinel isolation harness for ClaudeCodeRunner.

Plants unique, recognisable sentinel strings in a fake 'operator home' across
every isolation channel (CLAUDE.md, skills, settings.json, CLAUDE_CONFIG_DIR,
gitconfig email, env token) and asserts that none appear in the real
trajectory.jsonl emitted by the live claude CLI.

THIS FILE IS NOT EXECUTED IN NORMAL CI.  The entire module is skipped unless
AB_RUN_LIVE_ISOLATION=1 is set.  Running it spawns a real claude subprocess
and costs real tokens (or subscription quota).

Auth resolves automatically from whichever credential is present in the
environment: CLAUDE_CODE_OAUTH_TOKEN (Max subscription OAuth token, issued by
`claude setup-token`), ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN (pay-per-token
paths), or the macOS keychain subscription if none of the above are set.

Usage (opt-in only):
    # Subscription path (OAuth token):
    AB_RUN_LIVE_ISOLATION=1 CLAUDE_CODE_OAUTH_TOKEN=<token> \\
        uv run pytest -m live_isolation -v

    # API-key path:
    AB_RUN_LIVE_ISOLATION=1 ANTHROPIC_API_KEY=sk-ant-... \\
        uv run pytest -m live_isolation -v

    # macOS keychain path (logged-in Claude subscription, no token export needed):
    AB_RUN_LIVE_ISOLATION=1 uv run pytest -m live_isolation -v

Design
======
* A unique UUID sentinel is planted in each isolation channel.
* ClaudeCodeRunner is given the fake operator home as HOME.
* The runner executes a trivial task (write hello.txt) against the real claude
  CLI with ``use_fake_home=True``; --bare is omitted on the subscription paths.
* The resulting trajectory.jsonl is searched for each sentinel.
* Any hit → isolation failure for that channel.

Channels tested (one test per channel):
    B1 — CLAUDE.md sentinel in ~/.claude/CLAUDE.md
    B2 — skills sentinel in ~/.claude/skills/SENTINEL_SKILL/SKILL.md
    B3 — settings.json sentinel in ~/.claude/settings.json
    B4 — CLAUDE_CONFIG_DIR env override points back to op home
    B5 — gitconfig user.email sentinel (operator's ~/.gitconfig)
    B6 — env token sentinel (NOT in ALLOWED_ENV_KEYS) absent from trajectory
"""

from __future__ import annotations

import json
import os
import textwrap
import uuid
from pathlib import Path

import pytest
from ab_harness.runners.claude_code import ClaudeCodeRunner
from ab_harness.trajectory.writer import TrajectoryWriter

pytestmark = pytest.mark.live_isolation

_LIVE = os.environ.get("AB_RUN_LIVE_ISOLATION") == "1"

# Single guard applied to every test in this module.
# Auth resolves at runtime from whatever is in env (CLAUDE_CODE_OAUTH_TOKEN,
# ANTHROPIC_API_KEY) or the macOS keychain — no specific key required here.
skipif_not_live = pytest.mark.skipif(
    not _LIVE,
    reason=(
        "Gated live test: set AB_RUN_LIVE_ISOLATION=1 to run the live-sentinel "
        "harness (costs real tokens). Auth via CLAUDE_CODE_OAUTH_TOKEN, "
        "ANTHROPIC_API_KEY, or macOS keychain subscription."
    ),
)

# Trivial task: write hello.txt.  Short enough to resolve in one assistant turn.
_TASK_DESCRIPTION = "Write a file named hello.txt containing the word hello."
_TASK_CRITERIA = ["hello.txt exists and contains 'hello'."]


class _LiveTask:
    """Minimal Task duck-type sufficient for ClaudeCodeRunner."""

    id: str = "L0_live_sentinel"
    description: str = _TASK_DESCRIPTION
    acceptance_criteria: list[str] = _TASK_CRITERIA


# ---------------------------------------------------------------------------
# Fixture: fake operator home with all sentinel channels populated
# ---------------------------------------------------------------------------

@pytest.fixture()
def op_home_with_sentinels(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """Build a fake operator home.  Returns (home_path, {channel: sentinel})."""
    home = tmp_path / "op_home"
    claude = home / ".claude"
    claude.mkdir(parents=True)

    sentinels: dict[str, str] = {}

    # B1 — CLAUDE.md
    s1 = f"SENTINEL_CLAUDE_MD_{uuid.uuid4().hex}"
    (claude / "CLAUDE.md").write_text(
        f"# Operator instructions\n{s1}\n", encoding="utf-8"
    )
    sentinels["claude_md"] = s1

    # B2 — skills
    s2 = f"SENTINEL_SKILL_{uuid.uuid4().hex}"
    skill_dir = claude / "skills" / "sentinel-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"# Sentinel skill\n{s2}\n", encoding="utf-8"
    )
    sentinels["skill"] = s2

    # B3 — settings.json
    s3 = f"SENTINEL_SETTINGS_{uuid.uuid4().hex}"
    (claude / "settings.json").write_text(
        json.dumps({"_sentinel": s3, "env": {}}), encoding="utf-8"
    )
    sentinels["settings"] = s3

    # B4 — CLAUDE_CONFIG_DIR sentinel: plant a file the CLI might read if it
    # followed CLAUDE_CONFIG_DIR back to the op home.
    s4 = f"SENTINEL_CONFIG_DIR_{uuid.uuid4().hex}"
    (claude / "_config_dir_sentinel.txt").write_text(s4, encoding="utf-8")
    sentinels["config_dir"] = s4

    # B5 — gitconfig
    s5 = f"sentinel-{uuid.uuid4().hex}@noreply.test"
    gitconfig = home / ".gitconfig"
    gitconfig.write_text(
        textwrap.dedent(f"""\
            [user]
                name = Sentinel User
                email = {s5}
        """),
        encoding="utf-8",
    )
    sentinels["gitconfig"] = s5

    # B6 — env token (NOT in ALLOWED_ENV_KEYS).
    s6 = f"SENTINEL_ENV_TOKEN_{uuid.uuid4().hex}"
    sentinels["env_token"] = s6

    return home, sentinels


def _run_live_task(
    op_home: Path,
    env_sentinel: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    """Execute ClaudeCodeRunner against the real claude CLI.  Returns traj path."""
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    traj_path = tmp_path / "trajectory.jsonl"

    # Set operator HOME so IsolatedEnv sees it in os.environ.
    monkeypatch.setenv("HOME", str(op_home))
    # Plant the env token — must NOT reach claude via subprocess env.
    monkeypatch.setenv("SENTINEL_ENV_TOKEN_KEY", env_sentinel)
    # Also plant as CLAUDE_CONFIG_DIR → op home's .claude (belt-and-suspenders
    # test — IsolatedEnv should override this anyway).
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(op_home / ".claude"))

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_LiveTask(), writer, workdir=workdir)
    runner.cleanup()

    return traj_path


def _traj_text(traj_path: Path) -> str:
    """Return the full trajectory as a single string (for sentinel scanning)."""
    return traj_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# B1 — CLAUDE.md sentinel not in trajectory
# ---------------------------------------------------------------------------

@skipif_not_live
def test_b1_claude_md_sentinel_absent(
    op_home_with_sentinels: tuple[Path, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLAUDE.md operator instructions must not appear in trajectory."""
    op_home, sentinels = op_home_with_sentinels
    traj_path = _run_live_task(op_home, sentinels["env_token"], tmp_path, monkeypatch)
    text = _traj_text(traj_path)
    assert sentinels["claude_md"] not in text, (
        "CLAUDE.md sentinel found in trajectory — operator instructions leaked"
    )


# ---------------------------------------------------------------------------
# B2 — skills sentinel not in trajectory
# ---------------------------------------------------------------------------

@skipif_not_live
def test_b2_skill_sentinel_absent(
    op_home_with_sentinels: tuple[Path, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skill content from ~/.claude/skills/ must not appear in trajectory."""
    op_home, sentinels = op_home_with_sentinels
    traj_path = _run_live_task(op_home, sentinels["env_token"], tmp_path, monkeypatch)
    text = _traj_text(traj_path)
    assert sentinels["skill"] not in text, (
        "skills sentinel found in trajectory — operator skills leaked"
    )


# ---------------------------------------------------------------------------
# B3 — settings.json sentinel not in trajectory
# ---------------------------------------------------------------------------

@skipif_not_live
def test_b3_settings_sentinel_absent(
    op_home_with_sentinels: tuple[Path, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """settings.json operator config must not appear in trajectory."""
    op_home, sentinels = op_home_with_sentinels
    traj_path = _run_live_task(op_home, sentinels["env_token"], tmp_path, monkeypatch)
    text = _traj_text(traj_path)
    assert sentinels["settings"] not in text, (
        "settings.json sentinel found in trajectory — operator settings leaked"
    )


# ---------------------------------------------------------------------------
# B4 — CLAUDE_CONFIG_DIR can't redirect to operator home
# ---------------------------------------------------------------------------

@skipif_not_live
def test_b4_config_dir_sentinel_absent(
    op_home_with_sentinels: tuple[Path, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLAUDE_CONFIG_DIR belt-and-suspenders: config-dir sentinel not in trajectory."""
    op_home, sentinels = op_home_with_sentinels
    traj_path = _run_live_task(op_home, sentinels["env_token"], tmp_path, monkeypatch)
    text = _traj_text(traj_path)
    assert sentinels["config_dir"] not in text, (
        "config_dir sentinel found in trajectory — CLAUDE_CONFIG_DIR redirect failed"
    )


# ---------------------------------------------------------------------------
# B5 — gitconfig email sentinel not in trajectory
# ---------------------------------------------------------------------------

@skipif_not_live
def test_b5_gitconfig_sentinel_absent(
    op_home_with_sentinels: tuple[Path, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator gitconfig user.email must not appear in trajectory."""
    op_home, sentinels = op_home_with_sentinels
    traj_path = _run_live_task(op_home, sentinels["env_token"], tmp_path, monkeypatch)
    text = _traj_text(traj_path)
    assert sentinels["gitconfig"] not in text, (
        "gitconfig sentinel found in trajectory — operator git identity leaked"
    )


# ---------------------------------------------------------------------------
# B6 — env token sentinel not in subprocess env → not in trajectory
# ---------------------------------------------------------------------------

@skipif_not_live
def test_b6_env_token_sentinel_absent(
    op_home_with_sentinels: tuple[Path, dict[str, str]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator env token (not in ALLOWED_ENV_KEYS) must not appear in trajectory."""
    op_home, sentinels = op_home_with_sentinels
    traj_path = _run_live_task(op_home, sentinels["env_token"], tmp_path, monkeypatch)
    text = _traj_text(traj_path)
    assert sentinels["env_token"] not in text, (
        "env token sentinel found in trajectory — secret env var leaked"
    )
