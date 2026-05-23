"""ClaudeCodeRunner exercised against a mocked Popen that replays a canned stream-json fixture."""

from __future__ import annotations

import io
import json
import platform
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ab_harness.runners.claude_code import ClaudeCodeRunner
from ab_harness.trajectory.validate import validate
from ab_harness.trajectory.writer import TrajectoryWriter

FIXTURE = Path(__file__).parent / "fixtures" / "claude_code_stream_smoke.jsonl"


class _FakeProc:
    """Minimal subprocess.Popen stand-in driven by a fixture file."""

    def __init__(self, stdout_text: str, args: list[str] | None = None) -> None:
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO("")
        self.stdin = io.StringIO()
        self.returncode = 0
        self.args = args or []
        self._killed = False

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def kill(self) -> None:
        self._killed = True

    def communicate(self, input=None, timeout=None):
        return self.stdout.getvalue(), self.stderr.getvalue()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.fixture
def canned_stream() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def _make_task() -> Any:
    class _Task:
        id: ClassVar[str] = "L0_demo"
        description: ClassVar[str] = (
            "Create a file named hello.txt with the words 'hello world'."
        )
        acceptance_criteria: ClassVar[list[str]] = [
            "hello.txt exists in the working directory.",
            "Its contents include the string 'hello world'.",
        ]

    return _Task()


def _patch_popen(monkeypatch: pytest.MonkeyPatch, canned: str, on_run=None) -> None:
    def fake_popen(argv, **kwargs):
        if "--version" in argv:
            return _FakeProc("1.2.3\n", args=argv)
        if on_run is not None:
            on_run(argv, kwargs)
        return _FakeProc(canned, args=argv)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


def test_runner_emits_expected_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str) -> None:
    traj_path = tmp_path / "trajectory.jsonl"
    workdir = tmp_path / "vault"
    workdir.mkdir()

    seen: dict = {}

    def on_run(argv, kwargs):
        seen["argv"] = argv

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _patch_popen(monkeypatch, canned_stream, on_run=on_run)

    runner = ClaudeCodeRunner(model="claude-sonnet-4-5")
    runner.prepare(None)

    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)

    runner.cleanup()

    argv = seen["argv"]
    assert argv[0] == "claude"
    assert "--print" in argv
    assert "--output-format" in argv and "stream-json" in argv
    assert "--dangerously-skip-permissions" in argv

    assert str(status) in {"completed", "RunStatus.completed"} or getattr(status, "value", None) == "completed"

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    kinds = [e["event"] for e in events]

    assert kinds[0] == "run_start"
    assert kinds[-1] == "run_end"

    turns = [e for e in events if e["event"] == "turn"]
    assert len([t for t in turns if t["role"] == "assistant"]) == 2
    assert len([t for t in turns if t["role"] == "tool"]) == 1

    run_start = events[0]
    assert run_start["task_id"] == "L0_demo"
    assert run_start["model"] == "claude-sonnet-4-5"
    assert run_start["harness"].startswith("claude-code-cli@")
    assert run_start["tier"] == "T0"

    run_end = events[-1]
    assert run_end["status"] == "completed"
    assert run_end["totals"]["cost_usd"] > 0
    assert run_end["totals"]["latency_ms"] > 0

    first_assistant = next(t for t in turns if t["role"] == "assistant")
    assert any(tc["name"] == "Write" for tc in first_assistant["tool_calls"])
    assert first_assistant["tokens_in"] == 1200
    assert first_assistant["tokens_out"] == 40

    tool_turn = next(t for t in turns if t["role"] == "tool")
    assert tool_turn["tool_returns"]
    assert tool_turn["tool_returns"][0]["tool_use_id"] == "toolu_01"

    assert validate(traj_path) == []


def test_runner_records_vault_diff_when_files_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    traj_path = tmp_path / "trajectory.jsonl"
    workdir = tmp_path / "vault2"
    workdir.mkdir()

    def on_run(argv, kwargs):
        cwd = Path(kwargs["cwd"])
        (cwd / "hello.txt").write_text("hello world\n", encoding="utf-8")

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _patch_popen(monkeypatch, canned_stream, on_run=on_run)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assistant_turns = [e for e in events if e["event"] == "turn" and e["role"] == "assistant"]
    last_assistant = assistant_turns[-1]
    assert last_assistant["vault_state_diff"] is not None
    assert "hello.txt" in last_assistant["vault_state_diff"]["created"]


def test_runner_version_falls_back_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no claude binary in test env")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = ClaudeCodeRunner()
    assert runner.version() == "claude-code-cli@unknown"


def test_runner_requires_api_key_on_clean_home_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    """No API key on Linux → IsolationError before Popen (no keychain fallback)."""
    from ab_harness.runners.claude_code import IsolationError

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    # Force Linux so the macOS keychain branch is not taken.
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    workdir = tmp_path / "v"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    popen_called = []

    def on_run(argv, kwargs):
        popen_called.append(True)

    _patch_popen(monkeypatch, canned_stream, on_run=on_run)
    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer, pytest.raises(IsolationError, match="ANTHROPIC_API_KEY"):
        runner.run_task(_make_task(), writer, workdir=workdir)
    assert not popen_called, "Popen must NOT be called when API key is absent"


def test_run_start_carries_prompt_identity_from_materialized_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    """run_start records tier_hash (wrinkle fix), prompt_label, and the
    verbatim custom CLAUDE.md text — the prompt-as-row-identity contract."""
    from ab_datasets.schemas import Tier
    from ab_harness.sandbox.docker import MaterializedTier

    workdir = tmp_path / "wd"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"

    materialized = MaterializedTier(
        tier=Tier.T0,
        tier_hash="a" * 64,
        workdir=workdir,
        manifest_path=tmp_path / "manifest.yaml",
        claude_md_text="# Karpathy rules\nBe terse.\n",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _patch_popen(monkeypatch, canned_stream)
    runner = ClaudeCodeRunner(prompt_label="karpathy-rules")
    runner.prepare(materialized)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    run_start = events[0]
    # Wrinkle fix: tier_hash is read off MaterializedTier.tier_hash, not the
    # absent .total_sha256 — so it is non-None at runtime now.
    assert run_start["tier_hash"] == "a" * 64
    assert run_start["prompt_label"] == "karpathy-rules"
    # Verbatim prompt is embedded in system_prompt_verbatim (privacy gate
    # scans this trajectory line; reveal endpoint reads it).
    assert "# Karpathy rules" in run_start["system_prompt_verbatim"]
    assert "Be terse." in run_start["system_prompt_verbatim"]
    assert validate(traj_path) == []


def test_run_start_tier_hash_none_without_tier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    """No tier prepared → tier_hash None, system_prompt_verbatim unchanged."""
    workdir = tmp_path / "wd2"
    workdir.mkdir()
    traj_path = tmp_path / "t2.jsonl"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _patch_popen(monkeypatch, canned_stream)
    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    run_start = events[0]
    assert run_start["tier_hash"] is None
    assert run_start["prompt_label"] is None
    assert "--- project CLAUDE.md ---" not in run_start["system_prompt_verbatim"]
