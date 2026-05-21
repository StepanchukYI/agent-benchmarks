"""Workdir scrubbing — absolute paths in tool_call args/tool_returns must be normalized to ./ form."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ab_harness.runners.claude_code import (
    _SANDBOX_SYSTEM_PROMPT,
    ClaudeCodeRunner,
    _scrub_home,
    _scrub_turn,
    _scrub_workdir,
)
from ab_harness.trajectory.writer import TrajectoryWriter


class _FakeProc:
    def __init__(self, stdout_text: str, args: list[str] | None = None) -> None:
        self.stdout = io.StringIO(stdout_text)
        self.stderr = io.StringIO("")
        self.stdin = io.StringIO()
        self.returncode = 0
        self.args = args or []

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def poll(self) -> int:
        return self.returncode

    def kill(self) -> None:
        return None

    def communicate(self, input: Any = None, timeout: float | None = None) -> tuple[str, str]:
        out = self.stdout.read() if self.stdout else ""
        err = self.stderr.read() if self.stderr else ""
        return out, err

    def __enter__(self) -> _FakeProc:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def _make_task() -> Any:
    class _Task:
        id: ClassVar[str] = "L0_demo"
        description: ClassVar[str] = "noop"
        acceptance_criteria: ClassVar[list[str]] = ["noop"]

    return _Task()


def test_scrub_workdir_string_exact_match() -> None:
    assert _scrub_workdir("/abs/workdir", "/abs/workdir") == "."


def test_scrub_workdir_string_prefix() -> None:
    assert _scrub_workdir("/abs/workdir/foo/bar.txt", "/abs/workdir") == "./foo/bar.txt"


def test_scrub_workdir_embedded_in_text() -> None:
    out = _scrub_workdir(
        "File written to /abs/workdir/notes/x.txt successfully",
        "/abs/workdir",
    )
    assert out == "File written to ./notes/x.txt successfully"


def test_scrub_workdir_deep_dict_and_list() -> None:
    value = {
        "file_path": "/abs/workdir/foo/bar.txt",
        "items": ["/abs/workdir/a", "untouched", {"p": "/abs/workdir/b"}],
        "n": 42,
    }
    scrubbed = _scrub_workdir(value, "/abs/workdir")
    assert scrubbed["file_path"] == "./foo/bar.txt"
    assert scrubbed["items"][0] == "./a"
    assert scrubbed["items"][1] == "untouched"
    assert scrubbed["items"][2]["p"] == "./b"
    assert scrubbed["n"] == 42


def test_scrub_turn_normalizes_tool_call_args_and_tool_returns() -> None:
    turn = {
        "tool_calls": [
            {"id": "t1", "name": "Write", "args": {"file_path": "/abs/workdir/foo/bar.txt"}},
        ],
        "tool_returns": [
            {"tool_use_id": "t1", "detail": "wrote /abs/workdir/foo/bar.txt", "is_error": False},
        ],
    }
    out = _scrub_turn(turn, "/abs/workdir")
    assert out["tool_calls"][0]["args"]["file_path"] == "./foo/bar.txt"
    assert out["tool_returns"][0]["detail"] == "wrote ./foo/bar.txt"


def test_runner_writes_relative_paths_for_workdir_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: stream-json with absolute workdir paths produces trajectory with ./ form."""
    workdir = tmp_path / "vault"
    workdir.mkdir()
    workdir_abs = str(workdir.resolve())

    leaked_path = f"{workdir_abs}/notes/greeting.txt"

    stream_events = [
        {"type": "system", "subtype": "init"},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_01",
                        "name": "Write",
                        "input": {"file_path": leaked_path, "content": "hi"},
                    },
                ],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_01",
                        "is_error": False,
                        "content": [{"type": "text", "text": f"File written to {leaked_path}"}],
                    },
                ],
            },
        },
        {
            "type": "result",
            "subtype": "success",
            "total_cost_usd": 0.001,
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "duration_ms": 100,
        },
    ]
    canned = "\n".join(json.dumps(e) for e in stream_events) + "\n"

    def fake_popen(argv, **kwargs):
        if "--version" in argv:
            return _FakeProc("1.2.3\n", args=argv)
        return _FakeProc(canned, args=argv)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    traj_path = tmp_path / "trajectory.jsonl"
    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    text = traj_path.read_text(encoding="utf-8")
    assert workdir_abs not in text, "absolute workdir path leaked into trajectory"

    events = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    turns = [e for e in events if e["event"] == "turn"]
    assistant = next(t for t in turns if t["role"] == "assistant")
    assert assistant["tool_calls"][0]["args"]["file_path"] == "./notes/greeting.txt"
    tool = next(t for t in turns if t["role"] == "tool")
    assert tool["tool_returns"][0]["detail"] == "File written to ./notes/greeting.txt"


def test_scrub_home_replaces_user_home_with_tilde() -> None:
    assert _scrub_home("/Users/alice/project/file.txt", "/Users/alice") == "~/project/file.txt"


def test_argv_contains_append_system_prompt() -> None:
    runner = ClaudeCodeRunner()
    argv = runner._build_argv()
    assert "--append-system-prompt" in argv
    idx = argv.index("--append-system-prompt")
    assert argv[idx + 1] == _SANDBOX_SYSTEM_PROMPT
