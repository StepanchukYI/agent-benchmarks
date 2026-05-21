"""Subprocess-env isolation invariants for native runners.

Without these tests the runner CAN regress to ``os.environ.copy()`` and
silently leak the operator's ~/.claude/{CLAUDE.md, skills, settings.json}
+ arbitrary secrets (COMFY_*, OBSIDIAN_*) into the benchmark agent's
process.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from ab_harness.runners._isolation import ALLOWED_ENV_KEYS, IsolatedEnv


def test_isolation_drops_non_whitelisted_keys() -> None:
    fake_environ = {
        "PATH": "/usr/bin:/bin",
        "ANTHROPIC_API_KEY": "sk-ant-test",
        "COMFY_CONFLUENCE_API_TOKEN": "must-not-leak",
        "OBSIDIAN_API_KEY": "must-not-leak",
        "AB_API_BASE_URL": "must-not-leak",
        "VAULT_HUB": "must-not-leak",
        "HOME": "/Users/operator",
    }
    with mock.patch.dict(os.environ, fake_environ, clear=True):
        iso = IsolatedEnv.build()
    try:
        # Anthropic key survives.
        assert iso.env.get("ANTHROPIC_API_KEY") == "sk-ant-test"
        # PATH survives.
        assert "PATH" in iso.env
        # Operator secrets dropped.
        assert "COMFY_CONFLUENCE_API_TOKEN" not in iso.env
        assert "OBSIDIAN_API_KEY" not in iso.env
        assert "AB_API_BASE_URL" not in iso.env
        assert "VAULT_HUB" not in iso.env
        # HOME is rewritten to a fresh temp, NOT operator's real home.
        assert iso.env["HOME"] != "/Users/operator"
        assert iso.env["HOME"] == str(iso.fake_home)
        assert iso.fake_home.exists()
    finally:
        iso.cleanup()
    assert not iso.fake_home.exists()


def test_isolation_creates_empty_claude_dir() -> None:
    """Without an empty .claude in the fake HOME, claude CLI may write there
    during its own bootstrap and race with concurrent runs."""
    with mock.patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
        iso = IsolatedEnv.build()
    try:
        claude_dir = iso.fake_home / ".claude"
        assert claude_dir.is_dir()
        # No CLAUDE.md, no skills, no agents — fake home is BLANK.
        assert not (claude_dir / "CLAUDE.md").exists()
        assert not (claude_dir / "skills").exists()
        assert not (claude_dir / "agents").exists()
        assert not (claude_dir / "settings.json").exists()
    finally:
        iso.cleanup()


def test_isolation_redirects_xdg_dirs() -> None:
    """CLIs that follow the XDG spec must land inside fake_home, not in
    the operator's ~/.config / ~/.cache."""
    with mock.patch.dict(
        os.environ,
        {
            "PATH": "/usr/bin",
            "XDG_CONFIG_HOME": "/Users/operator/.config",
            "XDG_CACHE_HOME": "/Users/operator/.cache",
        },
        clear=True,
    ):
        iso = IsolatedEnv.build()
    try:
        assert iso.env["XDG_CONFIG_HOME"].startswith(str(iso.fake_home))
        assert iso.env["XDG_CACHE_HOME"].startswith(str(iso.fake_home))
        assert iso.env["XDG_STATE_HOME"].startswith(str(iso.fake_home))
    finally:
        iso.cleanup()


def test_env_overrides_win_last() -> None:
    """Vendor-routing overrides must override even whitelisted keys —
    operators legitimately re-point ANTHROPIC_BASE_URL per run."""
    with mock.patch.dict(
        os.environ,
        {
            "PATH": "/usr/bin",
            "ANTHROPIC_BASE_URL": "https://api.anthropic.com",
            "ANTHROPIC_AUTH_TOKEN": "operator-default",
        },
        clear=True,
    ):
        iso = IsolatedEnv.build(
            env_overrides={
                "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
                "ANTHROPIC_AUTH_TOKEN": "glm-token",
            }
        )
    try:
        assert iso.env["ANTHROPIC_BASE_URL"] == "https://api.z.ai/api/anthropic"
        assert iso.env["ANTHROPIC_AUTH_TOKEN"] == "glm-token"
    finally:
        iso.cleanup()


def test_cleanup_is_idempotent() -> None:
    with mock.patch.dict(os.environ, {"PATH": "/usr/bin"}, clear=True):
        iso = IsolatedEnv.build()
    iso.cleanup()
    iso.cleanup()  # no raise
    assert not iso.fake_home.exists()


def test_extra_keep_widens_whitelist() -> None:
    with mock.patch.dict(
        os.environ,
        {
            "PATH": "/usr/bin",
            "AB_CUSTOM_FLAG": "1",
            "COMFY_CONFLUENCE_API_TOKEN": "must-not-leak",
        },
        clear=True,
    ):
        iso = IsolatedEnv.build(extra_keep=frozenset({"AB_CUSTOM_FLAG"}))
    try:
        assert iso.env.get("AB_CUSTOM_FLAG") == "1"
        # extra_keep does NOT auto-widen to other operator keys.
        assert "COMFY_CONFLUENCE_API_TOKEN" not in iso.env
    finally:
        iso.cleanup()


@pytest.mark.parametrize(
    "key",
    [
        "PATH",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
    ],
)
def test_essential_keys_are_in_whitelist(key: str) -> None:
    """Pin the whitelist: dropping any of these would break a runner."""
    assert key in ALLOWED_ENV_KEYS


@pytest.mark.parametrize(
    "key",
    [
        # Operator-secret keys that MUST NOT survive isolation.
        "COMFY_CONFLUENCE_API_TOKEN",
        "OBSIDIAN_API_KEY",
        "AB_API_BASE_URL",
        "VAULT_HUB",
        "GITHUB_TOKEN",
        "ANTHROPIC_CLAUDE_CODE_USE_CLAUDE_MAX",
    ],
)
def test_known_leaky_keys_not_in_whitelist(key: str) -> None:
    """Pin the negative invariant: these specific keys MUST be dropped."""
    assert key not in ALLOWED_ENV_KEYS


def test_native_runners_use_isolation() -> None:
    """Every CLI-runner that calls subprocess.Popen MUST go through
    IsolatedEnv.build() — never os.environ.copy(). Pin by source grep."""
    runners_dir = Path(__file__).resolve().parents[1] / "ab_harness" / "runners"
    cli_runners = ["claude_code.py", "codex_cli.py", "gemini_cli.py", "opencode.py", "pi_agent.py"]
    for name in cli_runners:
        text = (runners_dir / name).read_text()
        assert "IsolatedEnv.build" in text, f"{name} must call IsolatedEnv.build()"
        # No raw env=os.environ.copy() in subprocess spawn paths.
        # (`os.environ.copy()` may still appear in unrelated paths, so the
        # tighter check is that env=os.environ.copy() is NOT passed to Popen.
        # The cleanest way is to ensure the runner has _isolated_env wiring.)
        assert "_isolated_env" in text, f"{name} must track an IsolatedEnv"


def test_subscription_runners_keep_real_home() -> None:
    """Runners whose CLI uses subscription auth (claude Max, codex ChatGPT,
    gemini OAuth, opencode multi-provider login, pi multi-provider login)
    must preserve the operator's real HOME so the keychain / oauth_creds /
    auth.json files are reachable. Pinned via source-grep for
    ``use_fake_home=False``."""
    runners_dir = Path(__file__).resolve().parents[1] / "ab_harness" / "runners"
    for name in ["claude_code.py", "codex_cli.py", "gemini_cli.py", "opencode.py", "pi_agent.py"]:
        text = (runners_dir / name).read_text()
        assert "use_fake_home=False" in text, (
            f"{name} must call IsolatedEnv.build(use_fake_home=False) so "
            f"subscription auth keeps working. Without this, the CLI cannot "
            f"reach ~/.{name.split('_')[0]}/ login state and the bench fails "
            f"with 'Not logged in'."
        )


def test_claude_argv_blocks_user_config_via_flags() -> None:
    """ClaudeCodeRunner must use claude CLI flags to block user-level
    contamination (since fake HOME would break Max auth). Pin the four
    critical flags."""
    runners_dir = Path(__file__).resolve().parents[1] / "ab_harness" / "runners"
    text = (runners_dir / "claude_code.py").read_text()
    for flag in [
        '"--system-prompt"',          # REPLACES default → blocks ~/.claude/CLAUDE.md
        '"--disable-slash-commands"', # blocks Skills
        '"--agents"',                 # '{}' overrides ~/.claude/agents/
        '"--strict-mcp-config"',      # blocks ~/.claude MCPs
    ]:
        assert flag in text, f"claude_code.py must build argv with {flag}"


def test_pi_argv_blocks_user_config_via_flags() -> None:
    runners_dir = Path(__file__).resolve().parents[1] / "ab_harness" / "runners"
    text = (runners_dir / "pi_agent.py").read_text()
    assert '"--system-prompt"' in text, "pi must REPLACE the default system prompt"
    assert '"--no-extensions"' in text, "pi must disable extension discovery"
    assert '"--no-session"' in text, "pi must run ephemeral (no session)"


def test_codex_argv_uses_strict_config() -> None:
    runners_dir = Path(__file__).resolve().parents[1] / "ab_harness" / "runners"
    text = (runners_dir / "codex_cli.py").read_text()
    assert '"--strict-config"' in text, "codex must use --strict-config"
    assert "shell_environment_policy.inherit=core" in text, (
        "codex must restrict child-shell env passthrough via "
        "shell_environment_policy.inherit=core override."
    )


def test_gemini_argv_blocks_extensions() -> None:
    runners_dir = Path(__file__).resolve().parents[1] / "ab_harness" / "runners"
    text = (runners_dir / "gemini_cli.py").read_text()
    # We pass -e with a non-matching sentinel name to load NO extensions.
    assert '"-e"' in text and "__ab_isolated__" in text, (
        "gemini must pass -e with a non-matching sentinel to block all "
        "user-installed extensions."
    )
