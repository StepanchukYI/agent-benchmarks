"""Subprocess isolation helpers — strip operator env, fake HOME, drop user CLI config.

Why this exists
================
Without isolation, `os.environ.copy()` leaks the operator's full shell into the
benchmark agent. Concretely:

* `HOME` points at the operator's real home → CLI tools (claude / codex /
  gemini / opencode / pi) auto-discover user-level config:
    ~/.claude/CLAUDE.md       — global instructions (memory)
    ~/.claude/skills/         — installed Skills (Skill tool surface)
    ~/.claude/agents/         — custom agent definitions
    ~/.claude/settings.json   — env injection (often with secrets)
    ~/.codex/, ~/.config/gh/, ~/.gemini/, ...
  All of these can change model behaviour at T0, contaminating "vanilla" runs.
* Environment carries arbitrary tokens (Confluence / Obsidian / GitHub /
  Anthropic / vendor SDKs) that the model sees in its tool environment and may
  echo back into the trajectory.

Isolation contract
==================
1. **HOME** is redirected to a fresh `tempfile.mkdtemp()`. We pre-create
   `<fake_home>/.claude` so the CLI doesn't try to write outside the temp.
2. **Env is built from a whitelist**, not via `copy()`. Only keys the CLI needs
   to do its job (PATH, locale, auth tokens for the target vendor) survive.
3. **Caller overrides win last** — `env_overrides` (vendor routing) is layered
   on top of the whitelisted env so per-run `ANTHROPIC_BASE_URL` /
   `ANTHROPIC_AUTH_TOKEN` work.
4. **Cleanup** removes the fake HOME on runner `.cleanup()`. Idempotent.

Usage
=====
```python
from ab_harness.runners._isolation import IsolatedEnv

iso = IsolatedEnv.build(env_overrides=self._env_overrides)
self._proc = subprocess.Popen(argv, env=iso.env, cwd=workdir, ...)
# later, on runner cleanup:
iso.cleanup()
```

Tests in `tests/test_runners_isolation.py` pin the invariants.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


# Env keys allowed through the isolation barrier. Anything outside this list is
# dropped before the subprocess sees it.
#
# Categorisation:
# * system basics — PATH, SHELL, terminal/locale
# * temp dirs — TMPDIR/TEMP/TMP
# * Anthropic native + Anthropic-compat (Zhipu/MiniMax/Moonshot/DeepSeek)
# * OpenAI native + OpenAI-compat (codex-cli / opencode / openai-compat)
# * Google native (gemini-cli)
# * Node basics (npm-managed CLIs)
# * CLI runtime toggles that operators legitimately set per-run (e.g.
#   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC, CLAUDE_BINARY)
ALLOWED_ENV_KEYS: frozenset[str] = frozenset(
    {
        # System basics
        "PATH",
        "SHELL",
        "TERM",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LC_MESSAGES",
        "USER",
        "USERNAME",
        "LOGNAME",
        # Temp
        "TMPDIR",
        "TEMP",
        "TMP",
        # Anthropic native + compat
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_MODEL",
        # Claude CLI runtime toggles (these don't leak operator config; they
        # just tell the binary how to behave)
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        "CLAUDE_CODE_NO_AUTOMATIC_UPDATES",
        "CLAUDE_BINARY",
        # OpenAI native + Codex CLI auth
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT",
        # Google Gemini native
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_GENAI_USE_GCA",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        # Node.js / npm-managed CLI basics
        "NODE_PATH",
        "NODE_OPTIONS",
        "NPM_CONFIG_PREFIX",
        # Python / uv basics (some CLIs shell back into python)
        "PYTHONPATH",
        "VIRTUAL_ENV",
        # System CA bundle (HTTPS works)
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
        # Proxy (some operators run behind one)
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "https_proxy",
        "http_proxy",
        "all_proxy",
        "no_proxy",
    }
)


@dataclass
class IsolatedEnv:
    """Built env + the fake HOME directory backing it. Caller owns cleanup."""

    env: dict[str, str]
    fake_home: Path

    @classmethod
    def build(
        cls,
        *,
        env_overrides: dict[str, str] | None = None,
        extra_keep: frozenset[str] | None = None,
    ) -> "IsolatedEnv":
        """Return a fresh `IsolatedEnv` ready to hand to `subprocess.Popen`.

        Parameters
        ----------
        env_overrides:
            Per-run env additions (vendor routing: ANTHROPIC_BASE_URL etc).
            Applied LAST so they always win.
        extra_keep:
            Optional additional whitelist keys, e.g. if a specific runner needs
            an environment variable the base whitelist doesn't cover. Avoid
            adding broad keys here; prefer the global whitelist.
        """
        allow = ALLOWED_ENV_KEYS | (extra_keep or frozenset())
        env: dict[str, str] = {k: os.environ[k] for k in allow if k in os.environ}

        # Fake HOME so the CLI's user-level config search misses the operator's
        # real ~/.claude/ etc. We pre-create the .claude subdir so the binary
        # doesn't have to mkdir into a path that might race with us.
        fake_home = Path(tempfile.mkdtemp(prefix="ab-isolated-home-"))
        (fake_home / ".claude").mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(fake_home)
        env["USERPROFILE"] = str(fake_home)  # Windows parity, harmless on Unix

        # XDG redirects so CLIs that follow the spec don't reach the
        # operator's ~/.config / ~/.cache / ~/.local.
        (fake_home / ".config").mkdir(parents=True, exist_ok=True)
        (fake_home / ".cache").mkdir(parents=True, exist_ok=True)
        (fake_home / ".local" / "state").mkdir(parents=True, exist_ok=True)
        env["XDG_CONFIG_HOME"] = str(fake_home / ".config")
        env["XDG_CACHE_HOME"] = str(fake_home / ".cache")
        env["XDG_STATE_HOME"] = str(fake_home / ".local" / "state")

        if env_overrides:
            env.update(env_overrides)

        return cls(env=env, fake_home=fake_home)

    def cleanup(self) -> None:
        """Remove the fake HOME. Idempotent."""
        if self.fake_home and self.fake_home.exists():
            shutil.rmtree(self.fake_home, ignore_errors=True)
