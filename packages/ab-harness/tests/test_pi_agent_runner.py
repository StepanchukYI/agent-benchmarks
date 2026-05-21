"""PiAgentRunner exercised against a mocked Popen that replays canned pi-cli JSONL streams."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ab_harness.runners.pi_agent import (
    _PI_THINKING_LEVELS,
    _SANDBOX_SYSTEM_PROMPT,
    PiAgentRunner,
)
from ab_harness.trajectory.validate import validate
from ab_harness.trajectory.writer import TrajectoryWriter


class _FakeProc:
    """Minimal subprocess.Popen stand-in driven by a fixture string."""

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

    def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[str, str]:
        return self.stdout.getvalue(), self.stderr.getvalue()

    def __enter__(self) -> _FakeProc:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


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


def _canned_stream(workdir_abs: str | None = None) -> str:
    """Build a realistic pi --mode json stream with tool_use + tool_result + message."""
    cmd_path = f"{workdir_abs}/hello.txt" if workdir_abs else "hello.txt"
    events = [
        {"type": "session", "session_id": "sess-abc", "model": "claude-sonnet-4-7"},
        {"type": "thinking", "content": "I should write the file with bash."},
        {
            "type": "tool_use",
            "id": "tool_1",
            "name": "bash",
            "input": {"command": f"echo 'hello world' > {cmd_path}"},
        },
        {
            "type": "tool_result",
            "tool_use_id": "tool_1",
            "output": "",
            "is_error": False,
        },
        {
            "type": "message",
            "role": "assistant",
            "content": "Done — wrote hello.txt.",
        },
        {"type": "usage", "usage": {"input_tokens": 1500, "output_tokens": 80}},
        {"type": "result", "status": "success", "duration_ms": 2500},
    ]
    return "\n".join(json.dumps(e) for e in events) + "\n"


def _patch_popen(
    monkeypatch: pytest.MonkeyPatch,
    canned: str,
    *,
    on_run: Any = None,
    raise_on_exec: bool = False,
) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    def fake_popen(argv, **kwargs):
        if raise_on_exec:
            raise FileNotFoundError("pi binary not found")
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        if on_run is not None:
            on_run(argv, kwargs)
        return _FakeProc(canned, args=argv)

    def fake_run(argv, *args, **kwargs):
        # Stub for `pi --version` probe.
        return subprocess.CompletedProcess(
            args=argv, returncode=0, stdout="pi-coding-agent 0.1.4\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_runner_argv_contains_required_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = PiAgentRunner(model="claude-sonnet-4-7")
    argv = runner._build_argv("hello prompt")
    assert argv[0] == "pi"
    assert "--mode" in argv
    assert argv[argv.index("--mode") + 1] == "json"
    assert "--print" in argv
    assert "--no-session" in argv
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "claude-sonnet-4-7"
    assert "--system-prompt" in argv
    # Sandbox preamble REPLACES default (blocks pi's own coding-assistant
    # framing + any user-level addons). Pair with --no-extensions which is
    # also asserted by the isolation test suite.
    assert argv[argv.index("--system-prompt") + 1] == _SANDBOX_SYSTEM_PROMPT
    assert "--no-extensions" in argv
    # Prompt is the trailing positional.
    assert argv[-1] == "hello prompt"


def test_runner_argv_includes_thinking_when_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = PiAgentRunner(model="claude-sonnet-4-7", effort="high")
    argv = runner._build_argv("p")
    assert "--thinking" in argv
    assert argv[argv.index("--thinking") + 1] == "high"


def test_runner_argv_drops_invalid_thinking_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # effort is recorded in trajectory but the CLI flag is dropped when
    # the value isn't in Pi's known --thinking set (so we don't kill the
    # run on a typo).
    runner = PiAgentRunner(model="claude-sonnet-4-7", effort="ultra")
    argv = runner._build_argv("p")
    assert "--thinking" not in argv
    assert runner._effort == "ultra"


def test_runner_argv_includes_provider_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = PiAgentRunner(model="claude-sonnet-4-7", provider="anthropic")
    argv = runner._build_argv("p")
    assert "--provider" in argv
    assert argv[argv.index("--provider") + 1] == "anthropic"


def test_pi_thinking_levels_match_cli_documented_set() -> None:
    # Hard guard: the harness's known set must stay 1:1 with Pi's CLI.
    assert _PI_THINKING_LEVELS == {
        "off",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
    }


def test_runner_emits_expected_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "vault"
    workdir.mkdir()
    canned = _canned_stream(workdir_abs=str(workdir.resolve()))
    seen = _patch_popen(monkeypatch, canned)

    runner = PiAgentRunner(model="claude-sonnet-4-7", effort="medium")
    runner.prepare(None)

    traj_path = tmp_path / "trajectory.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    # CLI was invoked with our expected argv.
    argv = seen["argv"]
    assert argv[0] == "pi"
    assert "--mode" in argv and argv[argv.index("--mode") + 1] == "json"

    assert (
        getattr(status, "value", None) == "completed"
        or str(status) in {"completed", "RunStatus.completed"}
    )

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run_start"
    assert kinds[-1] == "run_end"

    run_start = events[0]
    assert run_start["task_id"] == "L0_demo"
    assert run_start["model"] == "claude-sonnet-4-7"
    assert run_start["harness"].startswith("pi-agent@")
    assert run_start["tier"] == "T0"
    assert run_start["system_prompt_verbatim"] == _SANDBOX_SYSTEM_PROMPT
    assert run_start["reasoning"] == {"effort": "medium", "budget_tokens": None}
    # claude-sonnet-4-7 has 1_000_000 context window in the registry.
    assert run_start["model_context_window_tokens"] == 1_000_000

    turns = [e for e in events if e["event"] == "turn"]
    # Trajectory protocol requires: assistant turn carrying tool_calls
    # BEFORE the tool turn that carries the result. Plus a trailing
    # assistant turn for the final message.
    assistant_turns = [t for t in turns if t["role"] == "assistant"]
    tool_turns = [t for t in turns if t["role"] == "tool"]
    assert len(tool_turns) == 1
    assert len(assistant_turns) >= 1

    call_turn = assistant_turns[0]
    assert call_turn["tool_calls"], "expected first assistant turn to carry the tool_call"
    assert call_turn["tool_calls"][0]["name"] == "bash"
    # Workdir path inside the command must be scrubbed to "./hello.txt".
    cmd_str = call_turn["tool_calls"][0]["args"]["command"]
    assert "./hello.txt" in cmd_str
    assert str(workdir.resolve()) not in cmd_str

    tool = tool_turns[0]
    assert tool["tool_returns"][0]["tool_use_id"] == "tool_1"
    assert tool["tool_returns"][0]["is_error"] is False

    # Last assistant turn should carry the final agent message.
    final_assistant = assistant_turns[-1]
    assert "Done" in final_assistant["model_output"]

    # Strictly monotonic idx from 0.
    for i, t in enumerate(turns):
        assert t["idx"] == i

    run_end = events[-1]
    assert run_end["status"] == "completed"
    assert run_end["totals"]["tokens_in"] == 1500
    assert run_end["totals"]["tokens_out"] == 80
    # Cost backfilled via local pricing table (Pi exposes no cost field).
    assert run_end["totals"]["cost_usd"] > 0.0

    # Trajectory passes structural validation.
    assert validate(traj_path) == []


def test_runner_tool_result_marks_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    events = [
        {"type": "session", "session_id": "s"},
        {
            "type": "tool_use",
            "id": "t1",
            "name": "bash",
            "input": {"command": "false"},
        },
        {
            "type": "tool_result",
            "tool_use_id": "t1",
            "is_error": True,
            "output": "nope",
        },
        {"type": "usage", "input_tokens": 10, "output_tokens": 0},
        {"type": "result", "status": "success"},
    ]
    canned = "\n".join(json.dumps(e) for e in events) + "\n"
    _patch_popen(monkeypatch, canned)

    runner = PiAgentRunner(model="claude-sonnet-4-7")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    tool = next(e for e in parsed if e["event"] == "turn" and e["role"] == "tool")
    assert tool["tool_returns"][0]["is_error"] is True
    assert tool["tool_returns"][0]["detail"] == "nope"


def test_runner_handles_result_error_as_error_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    events = [
        {"type": "session", "session_id": "s"},
        {
            "type": "message",
            "role": "assistant",
            "content": "I cannot complete this.",
        },
        {"type": "result", "status": "error"},
    ]
    canned = "\n".join(json.dumps(e) for e in events) + "\n"
    _patch_popen(monkeypatch, canned)

    runner = PiAgentRunner(model="claude-sonnet-4-7")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert getattr(status, "value", None) == "error" or "error" in str(status)
    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assert parsed[-1]["event"] == "run_end"
    assert parsed[-1]["status"] == "error"


def test_runner_skips_non_json_stdout_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    # Pi may interleave non-JSON warnings; ensure we don't crash and
    # keep parsing.
    canned = (
        "not-json-warning-line\n"
        + json.dumps({"type": "session", "session_id": "s"})
        + "\n"
        + "another garbage line\n"
        + json.dumps({"type": "message", "role": "assistant", "content": "hi"})
        + "\n"
        + json.dumps({"type": "usage", "input_tokens": 5, "output_tokens": 3})
        + "\n"
        + json.dumps({"type": "result", "status": "success"})
        + "\n"
    )
    _patch_popen(monkeypatch, canned)

    runner = PiAgentRunner(model="claude-sonnet-4-7")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert getattr(status, "value", None) == "completed" or "completed" in str(status)
    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assistant = next(e for e in parsed if e["event"] == "turn" and e["role"] == "assistant")
    assert assistant["model_output"] == "hi"


def test_runner_drops_thinking_events_from_trajectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    events = [
        {"type": "session", "session_id": "s"},
        {"type": "thinking", "content": "Long internal reasoning..."},
        {"type": "thinking", "content": "More CoT..."},
        {"type": "message", "role": "assistant", "content": "Final answer."},
        {"type": "usage", "input_tokens": 100, "output_tokens": 5},
        {"type": "result", "status": "success"},
    ]
    canned = "\n".join(json.dumps(e) for e in events) + "\n"
    _patch_popen(monkeypatch, canned)

    runner = PiAgentRunner(model="claude-sonnet-4-7")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    # No turn should contain the raw CoT text.
    for e in parsed:
        if e["event"] == "turn":
            assert "Long internal reasoning" not in (e.get("model_output") or "")
            assert "More CoT" not in (e.get("model_output") or "")


def test_runner_missing_binary_writes_clean_run_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    _patch_popen(monkeypatch, "", raise_on_exec=True)

    runner = PiAgentRunner(model="claude-sonnet-4-7", binary="nonexistent-pi")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    # No Python crash; clean failure recorded.
    assert getattr(status, "value", None) == "error" or "error" in str(status)
    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assert parsed[0]["event"] == "run_start"
    assert parsed[-1]["event"] == "run_end"
    assert parsed[-1]["status"] == "error"


def test_runner_version_falls_back_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no pi binary in test env")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = PiAgentRunner()
    assert runner.version() == "pi-agent@unknown"


def test_runner_env_overrides_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    canned = (
        json.dumps({"type": "session", "session_id": "s"})
        + "\n"
        + json.dumps({"type": "result", "status": "success"})
        + "\n"
    )
    seen = _patch_popen(monkeypatch, canned)

    runner = PiAgentRunner(
        model="claude-sonnet-4-7",
        env_overrides={"ANTHROPIC_API_KEY": "sk-fake"},
    )
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    env_used = seen["kwargs"]["env"]
    assert env_used["ANTHROPIC_API_KEY"] == "sk-fake"


def test_factory_pi_agent_uses_real_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """factory.make_runner('pi-agent') returns a PiAgentRunner, not a StubRunner."""
    from ab_harness.runners.factory import StubRunner, make_runner

    runner = make_runner(runner="pi-agent", model="claude-sonnet-4-7")
    assert isinstance(runner, PiAgentRunner)
    assert not isinstance(runner, StubRunner)


def test_factory_pi_agent_forwards_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    from ab_harness.runners.factory import make_runner

    runner = make_runner(runner="pi-agent", model="claude-sonnet-4-7", effort="low")
    assert isinstance(runner, PiAgentRunner)
    assert runner._effort == "low"
    argv = runner._build_argv("p")
    assert "--thinking" in argv
    assert argv[argv.index("--thinking") + 1] == "low"


def test_factory_pi_agent_dropped_from_stub_reasons() -> None:
    from ab_harness.runners.factory import _STUB_REASONS

    assert "pi-agent" not in _STUB_REASONS
