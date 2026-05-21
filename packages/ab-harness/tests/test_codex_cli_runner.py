"""CodexCLIRunner exercised against a mocked Popen that replays a canned codex-cli JSONL stream."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ab_harness.runners.codex_cli import (
    _SANDBOX_SYSTEM_PROMPT,
    CodexCLIRunner,
    _scrub_turn,
    _scrub_workdir,
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
    """Build a realistic codex exec --json stream with command_execution + agent_message."""
    cmd_path = f"{workdir_abs}/hello.txt" if workdir_abs else "hello.txt"
    events = [
        {"type": "thread.started", "thread_id": "thread-abc"},
        {"type": "turn.started"},
        {
            "type": "item.started",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": f"echo 'hello world' > {cmd_path}",
                "aggregated_output": "",
                "exit_code": None,
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "command_execution",
                "command": f"echo 'hello world' > {cmd_path}",
                "aggregated_output": "",
                "exit_code": 0,
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "type": "agent_message",
                "text": "Done — wrote hello.txt.",
            },
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 2500,
                "cached_input_tokens": 2000,
                "output_tokens": 60,
                "reasoning_output_tokens": 40,
            },
        },
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
            raise FileNotFoundError("codex binary not found")
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        if on_run is not None:
            on_run(argv, kwargs)
        return _FakeProc(canned, args=argv)

    def fake_run(argv, *args, **kwargs):
        # Stub for `codex --version` probe.
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="codex-cli 0.132.0\n", stderr="")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_runner_argv_contains_required_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CodexCLIRunner(model="gpt-5.4")
    argv = runner._build_argv()
    assert argv[0] == "codex"
    assert "--ask-for-approval" in argv
    # Approval policy must appear before the `exec` subcommand (parent flag).
    assert argv.index("--ask-for-approval") < argv.index("exec")
    assert argv[argv.index("--ask-for-approval") + 1] == "never"
    assert "exec" in argv
    assert "--json" in argv
    assert "--sandbox" in argv
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert "--skip-git-repo-check" in argv
    assert "--ephemeral" in argv
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "gpt-5.4"
    # Prompt is fed via stdin: trailing "-".
    assert argv[-1] == "-"


def test_runner_argv_reasoning_effort_via_config(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CodexCLIRunner(model="gpt-5.4", reasoning_effort="high")
    argv = runner._build_argv()
    # Codex CLI exposes reasoning effort via the generic -c key=value override.
    assert "-c" in argv
    cidx = argv.index("-c")
    assert argv[cidx + 1] == "model_reasoning_effort=high"


def test_runner_emits_expected_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "vault"
    workdir.mkdir()
    canned = _canned_stream(workdir_abs=str(workdir.resolve()))
    seen = _patch_popen(monkeypatch, canned)

    runner = CodexCLIRunner(model="gpt-5.4", reasoning_effort="medium")
    runner.prepare(None)

    traj_path = tmp_path / "trajectory.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    # The CLI was invoked with our expected argv.
    argv = seen["argv"]
    assert "codex" in argv[0]
    assert "--json" in argv

    assert getattr(status, "value", None) == "completed" or str(status) in {"completed", "RunStatus.completed"}

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run_start"
    assert kinds[-1] == "run_end"

    run_start = events[0]
    assert run_start["task_id"] == "L0_demo"
    assert run_start["model"] == "gpt-5.4"
    assert run_start["harness"].startswith("codex-cli@")
    assert run_start["tier"] == "T0"
    assert run_start["system_prompt_verbatim"] == _SANDBOX_SYSTEM_PROMPT
    assert run_start["reasoning"] == {"effort": "medium"}
    # gpt-5.4 has 1_050_000 context window in the registry; record it.
    assert run_start["model_context_window_tokens"] == 1_050_000

    turns = [e for e in events if e["event"] == "turn"]
    # Trajectory protocol requires: tool_call in an assistant turn BEFORE the
    # tool turn that carries the result. So the canned stream produces:
    # assistant(tool_calls=[...]) → tool(tool_returns=[...]) → assistant(model_output=...)
    assistant_turns = [t for t in turns if t["role"] == "assistant"]
    tool_turns = [t for t in turns if t["role"] == "tool"]
    assert len(assistant_turns) == 2
    assert len(tool_turns) == 1

    call_turn = assistant_turns[0]
    assert call_turn["tool_calls"], "expected first assistant turn to carry the tool_call"
    assert call_turn["tool_calls"][0]["name"] == "shell"
    # Workdir path inside the command must be scrubbed to "./hello.txt".
    cmd_str = call_turn["tool_calls"][0]["args"]["command"]
    assert "./hello.txt" in cmd_str
    assert str(workdir.resolve()) not in cmd_str

    msg_turn = assistant_turns[1]
    assert msg_turn["model_output"] == "Done — wrote hello.txt."

    tool = tool_turns[0]
    assert tool["tool_returns"][0]["tool_use_id"] == "item_1"
    assert tool["tool_returns"][0]["is_error"] is False

    run_end = events[-1]
    assert run_end["status"] == "completed"
    # input_tokens + output_tokens + reasoning_output_tokens = 2500 + 60 + 40.
    assert run_end["totals"]["tokens_in"] == 2500
    assert run_end["totals"]["tokens_out"] == 60 + 40

    # Trajectory passes structural validation.
    assert validate(traj_path) == []


def test_runner_command_execution_failure_marks_tool_return_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    events = [
        {"type": "thread.started", "thread_id": "t"},
        {"type": "turn.started"},
        {
            "type": "item.started",
            "item": {"id": "i1", "type": "command_execution", "command": "false", "status": "in_progress"},
        },
        {
            "type": "item.completed",
            "item": {
                "id": "i1",
                "type": "command_execution",
                "command": "false",
                "exit_code": 1,
                "status": "failed",
                "aggregated_output": "nope",
            },
        },
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 0}},
    ]
    canned = "\n".join(json.dumps(e) for e in events) + "\n"
    _patch_popen(monkeypatch, canned)

    runner = CodexCLIRunner(model="gpt-5.4")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    tool = next(e for e in parsed if e["event"] == "turn" and e["role"] == "tool")
    assert tool["tool_returns"][0]["is_error"] is True
    assert tool["tool_returns"][0]["detail"] == "nope"


def test_runner_handles_turn_failed_as_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    events = [
        {"type": "thread.started", "thread_id": "t"},
        {"type": "turn.started"},
        {"type": "turn.failed", "error": {"message": "rate limited"}},
    ]
    canned = "\n".join(json.dumps(e) for e in events) + "\n"
    _patch_popen(monkeypatch, canned)

    runner = CodexCLIRunner(model="gpt-5.4")
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
    # Real codex sometimes interleaves stack traces / warnings; ensure we
    # don't crash and keep parsing.
    canned = (
        "not-json-warning-line\n"
        + json.dumps({"type": "thread.started", "thread_id": "t"})
        + "\n"
        + "another garbage line\n"
        + json.dumps({"type": "turn.started"})
        + "\n"
        + json.dumps(
            {
                "type": "item.completed",
                "item": {"id": "i", "type": "agent_message", "text": "hi"},
            }
        )
        + "\n"
        + json.dumps({"type": "turn.completed", "usage": {"input_tokens": 5, "output_tokens": 3}})
        + "\n"
    )
    _patch_popen(monkeypatch, canned)

    runner = CodexCLIRunner(model="gpt-5.4")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert getattr(status, "value", None) == "completed" or "completed" in str(status)
    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assistant = next(e for e in parsed if e["event"] == "turn" and e["role"] == "assistant")
    assert assistant["model_output"] == "hi"


def test_runner_missing_binary_writes_clean_run_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    _patch_popen(monkeypatch, "", raise_on_exec=True)

    runner = CodexCLIRunner(model="gpt-5.4", binary="nonexistent-codex")
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
        raise FileNotFoundError("no codex binary in test env")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = CodexCLIRunner()
    assert runner.version() == "codex-cli@unknown"


def test_scrub_workdir_inside_command_string() -> None:
    assert _scrub_workdir(
        "echo hi > /abs/workdir/foo.txt",
        "/abs/workdir",
    ) == "echo hi > ./foo.txt"


def test_scrub_turn_normalizes_command_args() -> None:
    turn = {
        "tool_calls": [
            {"id": "i1", "name": "shell", "args": {"command": "cat /abs/workdir/x.py"}},
        ],
        "tool_returns": [],
        "model_output": "wrote /abs/workdir/x.py",
    }
    out = _scrub_turn(turn, "/abs/workdir")
    assert out["tool_calls"][0]["args"]["command"] == "cat ./x.py"
    assert out["model_output"] == "wrote ./x.py"


def test_factory_codex_cli_uses_real_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """factory.make_runner('codex-cli') returns a CodexCLIRunner, not a StubRunner."""
    from ab_harness.runners.factory import StubRunner, make_runner

    runner = make_runner(runner="codex-cli", model="gpt-5.4")
    assert isinstance(runner, CodexCLIRunner)
    assert not isinstance(runner, StubRunner)


def test_factory_codex_cli_forwards_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    from ab_harness.runners.factory import make_runner

    runner = make_runner(runner="codex-cli", model="gpt-5.4", effort="low")
    assert isinstance(runner, CodexCLIRunner)
    assert runner._reasoning_effort == "low"
    argv = runner._build_argv()
    assert "model_reasoning_effort=low" in argv
