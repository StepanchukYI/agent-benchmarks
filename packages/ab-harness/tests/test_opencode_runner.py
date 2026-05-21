"""OpencodeRunner exercised against a mocked Popen that replays a canned opencode JSONL stream.

opencode's JSON event schema is not contractually stable as of v0.x, so
this test fixture pins a plausible event shape (text/tool_call/tool_result
with a final result event carrying aggregate usage) and verifies the
runner normalizes it into the shared trajectory protocol.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ab_harness.runners.opencode import (
    _EFFORT_TO_THINKING,
    _SANDBOX_HEADER_MARKER,
    _SANDBOX_SYSTEM_PROMPT,
    OpencodeRunner,
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
    """Build a plausible opencode `run --format json` stream.

    Event shapes here are best-effort — opencode v0.x does not publish a
    JSON schema. The runner is intentionally permissive about field
    naming (see _extract_text / _extract_usage / etype aliases).
    """
    cmd_path = f"{workdir_abs}/hello.txt" if workdir_abs else "hello.txt"
    events = [
        {"type": "message", "role": "assistant", "text": "Sure — writing the file.\n"},
        {
            "type": "tool_use",
            "id": "call_1",
            "name": "bash",
            "input": {"command": f"echo 'hello world' > {cmd_path}"},
        },
        {
            "type": "tool_result",
            "tool_use_id": "call_1",
            "is_error": False,
            "output": "",
        },
        {"type": "message", "role": "assistant", "text": "Done."},
        {
            "type": "result",
            "status": "success",
            "usage": {"input_tokens": 1200, "output_tokens": 45},
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
            raise FileNotFoundError("opencode binary not found")
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        if on_run is not None:
            on_run(argv, kwargs)
        return _FakeProc(canned, args=argv)

    def fake_run(argv, *args, **kwargs):
        # Stub for `opencode --version` probe.
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="0.1.0\n", stderr="")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    monkeypatch.setattr(subprocess, "run", fake_run)
    return seen


def test_runner_argv_contains_required_flags(tmp_path: Path) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    runner = OpencodeRunner(model="anthropic/claude-sonnet-4-5")
    argv = runner._build_argv(workdir=workdir)
    assert argv[0] == "opencode"
    assert "run" in argv
    assert "--format" in argv
    assert argv[argv.index("--format") + 1] == "json"
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "anthropic/claude-sonnet-4-5"
    assert "--dir" in argv
    assert argv[argv.index("--dir") + 1] == str(workdir)
    assert "--dangerously-skip-permissions" in argv


def test_runner_argv_includes_thinking_when_effort_set(tmp_path: Path) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    runner = OpencodeRunner(model="anthropic/claude-sonnet-4-5", effort="high")
    argv = runner._build_argv(workdir=workdir)
    assert "--thinking" in argv
    assert argv[argv.index("--thinking") + 1] == "high"


def test_effort_max_maps_to_xhigh_thinking() -> None:
    # max collapses to xhigh (opencode's ceiling) for parity with
    # ClaudeCodeRunner's --effort vocabulary.
    assert _EFFORT_TO_THINKING["max"] == "xhigh"
    assert _EFFORT_TO_THINKING["xhigh"] == "xhigh"
    assert _EFFORT_TO_THINKING["low"] == "low"
    assert _EFFORT_TO_THINKING["medium"] == "medium"
    assert _EFFORT_TO_THINKING["high"] == "high"


def test_runner_emits_expected_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "vault"
    workdir.mkdir()
    canned = _canned_stream(workdir_abs=str(workdir.resolve()))
    seen = _patch_popen(monkeypatch, canned)

    runner = OpencodeRunner(model="anthropic/claude-sonnet-4-5", effort="medium")
    runner.prepare(None)

    traj_path = tmp_path / "trajectory.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    # CLI invoked with expected argv (model + dir + format + thinking).
    argv = seen["argv"]
    assert "opencode" in argv[0]
    assert "--format" in argv
    assert "--thinking" in argv
    assert argv[argv.index("--thinking") + 1] == "medium"
    # Prompt is the trailing positional.
    assert "hello world" in argv[-1].lower() or "hello.txt" in argv[-1]

    # AGENTS.md staged in workdir with sandbox preamble.
    agents_md = workdir / "AGENTS.md"
    assert agents_md.exists()
    content = agents_md.read_text(encoding="utf-8")
    assert _SANDBOX_HEADER_MARKER in content
    assert _SANDBOX_SYSTEM_PROMPT in content

    assert getattr(status, "value", None) == "completed" or "completed" in str(status)

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run_start"
    assert kinds[-1] == "run_end"

    run_start = events[0]
    assert run_start["task_id"] == "L0_demo"
    assert run_start["model"] == "anthropic/claude-sonnet-4-5"
    assert run_start["harness"].startswith("opencode@")
    assert run_start["tier"] == "T0"
    assert run_start["system_prompt_verbatim"] == _SANDBOX_SYSTEM_PROMPT
    assert run_start["reasoning"] == {"effort": "medium", "budget_tokens": None}
    # claude-sonnet-4-5 has a non-zero context_window in the registry.
    assert run_start["model_context_window_tokens"] is not None
    assert run_start["model_context_window_tokens"] > 0

    turns = [e for e in events if e["event"] == "turn"]
    # Trajectory protocol: assistant(tool_calls) → tool(tool_returns) →
    # assistant(model_output). The canned stream produces exactly that.
    assistant_turns = [t for t in turns if t["role"] == "assistant"]
    tool_turns = [t for t in turns if t["role"] == "tool"]
    assert len(assistant_turns) == 2
    assert len(tool_turns) == 1

    call_turn = assistant_turns[0]
    assert call_turn["tool_calls"], "expected first assistant turn to carry the tool_call"
    assert call_turn["tool_calls"][0]["name"] == "bash"
    # Workdir path inside the command must be scrubbed to "./hello.txt".
    cmd_str = call_turn["tool_calls"][0]["args"]["command"]
    assert "./hello.txt" in cmd_str
    assert str(workdir.resolve()) not in cmd_str

    msg_turn = assistant_turns[1]
    assert "Done" in msg_turn["model_output"]

    tool = tool_turns[0]
    assert tool["tool_returns"][0]["tool_use_id"] == "call_1"
    assert tool["tool_returns"][0]["is_error"] is False

    # Trajectory idx is strictly monotonic from 0.
    idxs = [t["idx"] for t in turns]
    assert idxs == list(range(len(turns)))

    run_end = events[-1]
    assert run_end["status"] == "completed"
    assert run_end["totals"]["tokens_in"] == 1200
    assert run_end["totals"]["tokens_out"] == 45
    # Cost backfilled from pricing table.
    assert run_end["totals"]["cost_usd"] > 0.0

    # Trajectory passes structural validation.
    assert validate(traj_path) == []


def test_runner_skips_unknown_event_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Schema isn't stable yet — unknown event types must not crash."""
    workdir = tmp_path / "v"
    workdir.mkdir()
    events = [
        {"type": "session.started", "session_id": "abc"},  # unknown
        {"type": "weird_future_event", "payload": {"x": 1}},  # unknown
        {"type": "message", "role": "assistant", "text": "hi"},
        {"type": "result", "status": "success", "usage": {"input_tokens": 5, "output_tokens": 3}},
    ]
    canned = "\n".join(json.dumps(e) for e in events) + "\n"
    _patch_popen(monkeypatch, canned)

    runner = OpencodeRunner(model="anthropic/claude-sonnet-4-5")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert getattr(status, "value", None) == "completed" or "completed" in str(status)
    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assistant = next(e for e in parsed if e["event"] == "turn" and e["role"] == "assistant")
    assert assistant["model_output"] == "hi"


def test_runner_skips_non_json_stdout_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencode may interleave banner / warning lines on stdout; don't crash."""
    workdir = tmp_path / "v"
    workdir.mkdir()
    canned = (
        "Welcome to opencode v0.1.0\n"
        + json.dumps({"type": "message", "role": "assistant", "text": "hi"})
        + "\n"
        + "[warn] something\n"
        + json.dumps({"type": "result", "status": "success", "usage": {"input_tokens": 5, "output_tokens": 3}})
        + "\n"
    )
    _patch_popen(monkeypatch, canned)

    runner = OpencodeRunner(model="anthropic/claude-sonnet-4-5")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert getattr(status, "value", None) == "completed" or "completed" in str(status)
    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assistant = next(e for e in parsed if e["event"] == "turn" and e["role"] == "assistant")
    assert assistant["model_output"] == "hi"


def test_runner_tool_result_with_error_marks_is_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    events = [
        {"type": "tool_use", "id": "c1", "name": "bash", "input": {"command": "false"}},
        {"type": "tool_result", "tool_use_id": "c1", "is_error": True, "output": "nope"},
        {"type": "result", "status": "error", "usage": {"input_tokens": 10, "output_tokens": 0}},
    ]
    canned = "\n".join(json.dumps(e) for e in events) + "\n"
    _patch_popen(monkeypatch, canned)

    runner = OpencodeRunner(model="anthropic/claude-sonnet-4-5")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert getattr(status, "value", None) == "error" or "error" in str(status)
    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    tool = next(e for e in parsed if e["event"] == "turn" and e["role"] == "tool")
    assert tool["tool_returns"][0]["is_error"] is True
    assert tool["tool_returns"][0]["detail"] == "nope"


def test_runner_missing_binary_writes_clean_run_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    _patch_popen(monkeypatch, "", raise_on_exec=True)

    runner = OpencodeRunner(model="anthropic/claude-sonnet-4-5", binary="nonexistent-opencode")
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    # No Python crash; clean unrunnable recorded.
    assert getattr(status, "value", None) == "unrunnable" or "unrunnable" in str(status)
    parsed = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assert parsed[0]["event"] == "run_start"
    assert parsed[-1]["event"] == "run_end"
    assert parsed[-1]["status"] == "unrunnable"


def test_runner_version_falls_back_to_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no opencode binary in test env")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = OpencodeRunner()
    assert runner.version() == "opencode@unknown"


def test_runner_env_overrides_applied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "v"
    workdir.mkdir()
    canned = (
        json.dumps({"type": "message", "role": "assistant", "text": "ok"})
        + "\n"
        + json.dumps({"type": "result", "status": "success", "usage": {"input_tokens": 1, "output_tokens": 1}})
        + "\n"
    )
    seen = _patch_popen(monkeypatch, canned)

    runner = OpencodeRunner(
        model="anthropic/claude-sonnet-4-5",
        env_overrides={"ANTHROPIC_BASE_URL": "https://example.test/anthropic", "AB_FOO": "bar"},
    )
    runner.prepare(None)
    traj_path = tmp_path / "t.jsonl"
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    env = seen["kwargs"]["env"]
    assert env["ANTHROPIC_BASE_URL"] == "https://example.test/anthropic"
    assert env["AB_FOO"] == "bar"


def test_factory_opencode_uses_real_runner() -> None:
    """factory.make_runner('opencode') returns an OpencodeRunner, not a StubRunner."""
    from ab_harness.runners.factory import StubRunner, make_runner

    runner = make_runner(runner="opencode", model="anthropic/claude-sonnet-4-5")
    assert isinstance(runner, OpencodeRunner)
    assert not isinstance(runner, StubRunner)


def test_factory_opencode_forwards_effort() -> None:
    from ab_harness.runners.factory import make_runner

    runner = make_runner(runner="opencode", model="anthropic/claude-sonnet-4-5", effort="low")
    assert isinstance(runner, OpencodeRunner)
    assert runner._effort == "low"


def test_agents_md_preserves_existing_content(tmp_path: Path) -> None:
    """If AGENTS.md already exists, the sandbox preamble is prepended."""
    workdir = tmp_path / "v"
    workdir.mkdir()
    (workdir / "AGENTS.md").write_text("Operator instructions: be polite.\n", encoding="utf-8")

    from ab_harness.runners.opencode import _write_sandbox_agents_md

    _write_sandbox_agents_md(workdir)

    content = (workdir / "AGENTS.md").read_text(encoding="utf-8")
    assert _SANDBOX_HEADER_MARKER in content
    assert _SANDBOX_SYSTEM_PROMPT in content
    assert "Operator instructions: be polite." in content
    # Sandbox preamble should come first.
    assert content.index(_SANDBOX_HEADER_MARKER) < content.index("Operator instructions")


def test_agents_md_idempotent_on_rerun(tmp_path: Path) -> None:
    """Re-running the staging step on an already-staged workdir is a no-op."""
    workdir = tmp_path / "v"
    workdir.mkdir()

    from ab_harness.runners.opencode import _write_sandbox_agents_md

    _write_sandbox_agents_md(workdir)
    first = (workdir / "AGENTS.md").read_text(encoding="utf-8")
    _write_sandbox_agents_md(workdir)
    second = (workdir / "AGENTS.md").read_text(encoding="utf-8")
    assert first == second
