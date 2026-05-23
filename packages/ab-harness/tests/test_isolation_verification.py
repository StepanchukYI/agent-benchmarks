"""Tier A deterministic isolation verification suite for ClaudeCodeRunner.

Each test proves one leak channel is closed on the clean-HOME path. No live
model, no real ~/.claude mutation. Popen is mocked; Path.home() is redirected
to tmp_path fixtures.

Run the full suite:
    uv run pytest -m isolation -q
    make verify-isolation
"""

from __future__ import annotations

import hashlib
import io
import json
import platform
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ab_harness.runners.claude_code import ClaudeCodeRunner, IsolationError
from ab_harness.trajectory.writer import TrajectoryWriter

pytestmark = pytest.mark.isolation

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FIXTURE_STREAM = Path(__file__).parent / "fixtures" / "claude_code_stream_smoke.jsonl"


def _canned() -> str:
    return _FIXTURE_STREAM.read_text(encoding="utf-8")


class _FakeProc:
    """Minimal Popen stand-in."""

    def __init__(self, stdout_text: str = "") -> None:
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO("")
        self.stdin = io.StringIO()
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def kill(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_) -> None:
        pass


class _Task:
    id: ClassVar[str] = "L0_iso_test"
    description: ClassVar[str] = "Write hello.txt containing 'hello'."
    acceptance_criteria: ClassVar[list[str]] = ["hello.txt exists."]


def _make_task() -> Any:
    return _Task()


def _make_fake_op_home(base: Path) -> Path:
    """Create a fake 'operator home' with populated ~/.claude config files."""
    home = base / "op_home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("operator instructions", encoding="utf-8")
    (claude / "skills").mkdir()
    (claude / "skills" / "SKILL.md").write_text("skill content", encoding="utf-8")
    (claude / "plugins").mkdir()
    (claude / "settings.json").write_text('{"key": "value"}', encoding="utf-8")
    return home


def _hash_tree(root: Path) -> dict[str, str]:
    """Return {relpath: sha256hex} for every file under root."""
    result: dict[str, str] = {}
    if not root.exists():
        return result
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(root))
            result[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def _patch_popen(monkeypatch: pytest.MonkeyPatch, capture: dict | None = None) -> None:
    """Replace subprocess.Popen AND subprocess.run. Captures kwargs into `capture`."""
    canned = _canned()

    def fake_popen(argv, **kwargs):
        if capture is not None:
            capture["env"] = kwargs.get("env", {})
            capture["cwd"] = kwargs.get("cwd")
            capture["argv"] = argv
        return _FakeProc(canned)

    def fake_run(argv, **kwargs):
        # subprocess.run is used only for `claude --version`.
        return subprocess.CompletedProcess(argv, returncode=0, stdout="1.2.3\n", stderr="")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(subprocess, "run", fake_run)


# ---------------------------------------------------------------------------
# A1 — HOME redirect: subprocess sees temp HOME, not operator HOME
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a1_home_redirect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """env[HOME] passed to Popen must equal the IsolatedEnv temp dir,
    not the operator's real home."""
    op_home = _make_fake_op_home(tmp_path)
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    capture: dict = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("HOME", str(op_home))
    _patch_popen(monkeypatch, capture)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    proc_home = capture["env"]["HOME"]
    assert proc_home != str(op_home), "subprocess must NOT see the operator's real HOME"
    assert proc_home.startswith("/"), "HOME must be an absolute path"
    # The temp home must be a real directory that was created by IsolatedEnv.
    # (cleanup already removed it, but we captured it before cleanup.)
    assert "ab-isolated-home-" in proc_home or proc_home != str(op_home)
    assert capture["cwd"] == str(workdir)


# ---------------------------------------------------------------------------
# A2 — Temp HOME is empty of operator config
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a2_temp_home_empty_of_operator_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The temp HOME that the subprocess sees must contain NO operator config:
    no CLAUDE.md, no skills/, no agents/, no plugins/, no settings.json."""
    op_home = _make_fake_op_home(tmp_path)
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    captured_home: list[str] = []

    def fake_popen(argv, **kwargs):
        captured_home.append(kwargs["env"]["HOME"])
        return _FakeProc(_canned())

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode=0, stdout="1.2.3\n", stderr="")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("HOME", str(op_home))
    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    # Inspect temp home BEFORE cleanup removes it.
    temp_home = Path(captured_home[0])
    claude_dir = temp_home / ".claude"
    assert claude_dir.is_dir(), "temp HOME must have an empty .claude dir"
    for leaked in ["CLAUDE.md", "skills", "agents", "plugins", "settings.json"]:
        assert not (claude_dir / leaked).exists(), (
            f"temp HOME/.claude/{leaked} must be absent — operator config leaked"
        )
    runner.cleanup()


# ---------------------------------------------------------------------------
# A3 — Real ~/.claude byte-identical before/after INCLUDING abort paths
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a3_real_home_byte_identical_normal_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Normal run: operator home tree is byte-identical before and after run_task."""
    op_home = _make_fake_op_home(tmp_path)
    before = _hash_tree(op_home)

    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("HOME", str(op_home))
    _patch_popen(monkeypatch)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    after = _hash_tree(op_home)
    assert before == after, "operator home was mutated during a normal run"


@pytest.mark.isolation
def test_a3_real_home_byte_identical_popen_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Abort path — Popen raises mid-run: operator home still byte-identical."""
    op_home = _make_fake_op_home(tmp_path)
    before = _hash_tree(op_home)

    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    def raising_popen(argv, **kwargs):
        raise OSError("simulated Popen failure")

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode=0, stdout="1.2.3\n", stderr="")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("HOME", str(op_home))
    monkeypatch.setattr(subprocess, "Popen", raising_popen)
    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer, pytest.raises(OSError, match="simulated Popen failure"):
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    after = _hash_tree(op_home)
    assert before == after, "operator home was mutated when Popen raised"


@pytest.mark.isolation
def test_a3_real_home_byte_identical_after_cleanup_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """cleanup() after any exception must not touch operator home."""
    op_home = _make_fake_op_home(tmp_path)
    before = _hash_tree(op_home)

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("HOME", str(op_home))

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    # Simulate a mid-run IsolatedEnv having been built, then cleanup called.
    from ab_harness.runners._isolation import IsolatedEnv
    runner._isolated_env = IsolatedEnv.build(
        env_overrides={"ANTHROPIC_API_KEY": "sk-ant-test"},
        use_fake_home=True,
    )
    runner.cleanup()

    after = _hash_tree(op_home)
    assert before == after, "cleanup() mutated operator home"


# ---------------------------------------------------------------------------
# A4 — Env whitelist: planted secrets are not in subprocess env
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a4_env_whitelist_drops_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Operator secrets planted in os.environ must not reach subprocess env."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    capture: dict = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OBSIDIAN_TOKEN", "secret-obsidian")
    # Sentinel value (not a real AWS key; not an AWS canonical example string —
    # that would trip the privacy_check scanner's aws-access-key-id pattern in CI).
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "isolation-test-aws-sentinel")
    monkeypatch.setenv("FOO_SECRET", "my-private-value")
    monkeypatch.setenv("INTERNAL_WIKI_API_TOKEN", "wiki-secret")
    _patch_popen(monkeypatch, capture)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    env = capture["env"]
    # API key must survive (whitelisted).
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-test"
    # Operator secrets must be absent.
    assert "OBSIDIAN_TOKEN" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert "FOO_SECRET" not in env
    assert "INTERNAL_WIKI_API_TOKEN" not in env


# ---------------------------------------------------------------------------
# A5 — CLAUDE_CONFIG_DIR can't point at operator dir
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a5_claude_config_dir_overridden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if CLAUDE_CONFIG_DIR is set in the operator env to their real ~/.claude,
    the subprocess env must have it pointing at the temp dir — not the operator path."""
    op_home = _make_fake_op_home(tmp_path)
    op_claude = str(op_home / ".claude")

    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    capture: dict = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    # Plant operator CLAUDE_CONFIG_DIR — this is NOT in ALLOWED_ENV_KEYS but
    # we want to prove the belt-and-suspenders override in _isolation.py works
    # even if it were ever added to the whitelist.
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", op_claude)
    _patch_popen(monkeypatch, capture)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    env = capture["env"]
    # If CLAUDE_CONFIG_DIR is present in the subprocess env, it must NOT be
    # the operator's real ~/.claude.
    if "CLAUDE_CONFIG_DIR" in env:
        assert env["CLAUDE_CONFIG_DIR"] != op_claude, (
            "CLAUDE_CONFIG_DIR must not point at the operator's real ~/.claude"
        )
        assert "ab-isolated-home-" in env["CLAUDE_CONFIG_DIR"] or (
            env["CLAUDE_CONFIG_DIR"] != op_claude
        )


# ---------------------------------------------------------------------------
# A6 — Auth-mode decision: IsolationError on Linux no-key; bare on key path;
#       subscription (no --bare) on macOS no-key path
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a6_no_key_linux_raises_before_popen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No key + Linux → IsolationError before Popen (no keychain fallback)."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    popen_called: list[bool] = []

    def sentinel_popen(argv, **kwargs):
        popen_called.append(True)
        return _FakeProc(_canned())

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, returncode=0, stdout="1.2.3\n", stderr="")

    monkeypatch.setattr(subprocess, "Popen", sentinel_popen)
    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer, pytest.raises(IsolationError, match="ANTHROPIC_API_KEY"):
        runner.run_task(_make_task(), writer, workdir=workdir)

    assert not popen_called, "Popen must NOT be called when API key absent on Linux"


@pytest.mark.isolation
def test_a6_no_key_darwin_drops_bare_calls_popen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No key + macOS → no IsolationError, Popen called, argv has NO '--bare'."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")

    capture: dict = {}
    _patch_popen(monkeypatch, capture)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    # Must NOT raise IsolationError.
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert capture.get("argv") is not None, "Popen was not called on macOS no-key path"
    assert "--bare" not in capture["argv"], (
        "argv must NOT contain --bare on the macOS subscription path"
    )


@pytest.mark.isolation
def test_a6_key_present_uses_bare(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ANTHROPIC_API_KEY present → argv contains '--bare' (API-key auth path)."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    capture: dict = {}
    _patch_popen(monkeypatch, capture)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert "--bare" in capture["argv"], (
        "argv must contain --bare when ANTHROPIC_API_KEY is set"
    )


@pytest.mark.isolation
def test_a6_auth_token_accepted_as_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ANTHROPIC_AUTH_TOKEN (vendor-routing) is accepted as alternative to API key."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "sk-ant-oat-test")
    _patch_popen(monkeypatch)

    runner = ClaudeCodeRunner(env_overrides={"ANTHROPIC_AUTH_TOKEN": "sk-ant-oat-test"})
    runner.prepare(None)
    # Must NOT raise IsolationError.
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()


# ---------------------------------------------------------------------------
# A7 — PATH sanitize: operator-private dirs stripped
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a7_path_sanitize_drops_operator_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Operator-private PATH entries (home-rooted) must not reach the subprocess."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    fake_home = tmp_path / "fake_op_home"
    private_bin = fake_home / ".local" / "bin"
    private_bin.mkdir(parents=True)

    capture: dict = {}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("PATH", f"{private_bin}:/usr/bin:/bin")
    _patch_popen(monkeypatch, capture)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    proc_path = capture["env"].get("PATH", "")
    path_entries = proc_path.split(":")
    assert str(private_bin) not in path_entries, (
        f"operator-private PATH entry {private_bin} leaked into subprocess"
    )
    # System entries survive.
    assert any(e in ("/usr/bin", "/bin") for e in path_entries)


# ---------------------------------------------------------------------------
# A8 — isolation record on run_start reflects auth mode
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a8_isolation_record_key_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """API-key path: run_start isolation record has bare=True."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _patch_popen(monkeypatch)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    run_start = events[0]
    assert run_start["event"] == "run_start"

    iso = run_start.get("isolation")
    assert iso is not None, "run_start must carry an isolation record"
    assert iso["mode"] == "clean_home"
    assert iso["real_home_untouched"] is True
    assert iso["bare"] is True
    assert iso["home"].startswith("/")
    assert iso["home"] != str(Path.home())


@pytest.mark.isolation
def test_a8_isolation_record_macos_subscription_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """macOS subscription path (no API key): isolation record has bare=False."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    _patch_popen(monkeypatch)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    run_start = events[0]
    assert run_start["event"] == "run_start"

    iso = run_start.get("isolation")
    assert iso is not None, "run_start must carry an isolation record"
    assert iso["mode"] == "clean_home"
    assert iso["real_home_untouched"] is True
    assert iso["bare"] is False
    assert iso["home"].startswith("/")
    assert iso["home"] != str(Path.home())


# ---------------------------------------------------------------------------
# A9 — CLAUDE_CODE_OAUTH_TOKEN passes whitelist; unrelated secrets still drop
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a9_oauth_token_passes_whitelist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLAUDE_CODE_OAUTH_TOKEN is whitelisted → reaches subprocess env.
    Unrelated operator secrets (OBSIDIAN_TOKEN, FOO_SECRET) still dropped."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    capture: dict = {}
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-test-token-abc123")
    monkeypatch.setenv("OBSIDIAN_TOKEN", "secret-obsidian")
    monkeypatch.setenv("FOO_SECRET", "my-private-value")
    # Force Darwin so the OAuth path is taken (not the Linux IsolationError path).
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    _patch_popen(monkeypatch, capture)

    runner = ClaudeCodeRunner(env_overrides={"CLAUDE_CODE_OAUTH_TOKEN": "oat-test-token-abc123"})
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    env = capture["env"]
    # OAuth token must pass through (whitelisted).
    assert env.get("CLAUDE_CODE_OAUTH_TOKEN") == "oat-test-token-abc123", (
        "CLAUDE_CODE_OAUTH_TOKEN must reach the subprocess env"
    )
    # Unrelated secrets must still be dropped.
    assert "OBSIDIAN_TOKEN" not in env, "OBSIDIAN_TOKEN must not reach subprocess"
    assert "FOO_SECRET" not in env, "FOO_SECRET must not reach subprocess"


# ---------------------------------------------------------------------------
# A10 — OAuth token auth path: no raise, no --bare, Popen called, bare=False in record
# ---------------------------------------------------------------------------

@pytest.mark.isolation
def test_a10_oauth_token_no_bare_popen_called(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLAUDE_CODE_OAUTH_TOKEN (no API key) → no IsolationError, argv has NO '--bare',
    Popen is called, and isolation.bare is False in the run_start record."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oat-test-token-xyz789")
    # Platform-independent: OAuth path should work on Linux too.
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    capture: dict = {}
    _patch_popen(monkeypatch, capture)

    runner = ClaudeCodeRunner(env_overrides={"CLAUDE_CODE_OAUTH_TOKEN": "oat-test-token-xyz789"})
    runner.prepare(None)
    # Must NOT raise IsolationError.
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert capture.get("argv") is not None, "Popen was not called on OAuth path"
    assert "--bare" not in capture["argv"], (
        "argv must NOT contain --bare on the OAuth subscription path"
    )

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    run_start = events[0]
    iso = run_start.get("isolation")
    assert iso is not None, "run_start must carry an isolation record"
    assert iso["bare"] is False, "isolation.bare must be False on the OAuth path"
