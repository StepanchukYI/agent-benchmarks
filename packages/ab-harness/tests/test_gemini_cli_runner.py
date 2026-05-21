"""GeminiCLIRunner driven against a mocked Popen that replays canned stream-json.

Wire shape verified against ``@google/gemini-cli@0.20.2`` source (see
``ab_harness.runners.gemini_cli`` module docstring). The fixture
``gemini_cli_stream_smoke.jsonl`` is hand-written to match that exact
shape — keep them in sync if Google ships breaking event-schema changes.
"""

from __future__ import annotations

import io
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ab_harness.runners.gemini_cli import (
    _SANDBOX_HEADER_MARKER,
    _SANDBOX_SYSTEM_PROMPT,
    GeminiCLIRunner,
)
from ab_harness.trajectory.validate import validate
from ab_harness.trajectory.writer import TrajectoryWriter

FIXTURE = Path(__file__).parent / "fixtures" / "gemini_cli_stream_smoke.jsonl"


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
            return _FakeProc("0.20.2\n", args=argv)
        if on_run is not None:
            on_run(argv, kwargs)
        return _FakeProc(canned, args=argv)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


def test_runner_emits_expected_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    traj_path = tmp_path / "trajectory.jsonl"
    workdir = tmp_path / "vault"
    workdir.mkdir()

    seen: dict = {}

    def on_run(argv, kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs.get("cwd")

    _patch_popen(monkeypatch, canned_stream, on_run=on_run)

    runner = GeminiCLIRunner(model="gemini-3-pro")
    runner.prepare(None)

    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)

    runner.cleanup()

    argv = seen["argv"]
    assert argv[0] == "gemini"
    assert "--output-format" in argv and "stream-json" in argv
    assert "--model" in argv
    assert "--yolo" in argv

    assert (
        str(status) in {"completed", "RunStatus.completed"}
        or getattr(status, "value", None) == "completed"
    )

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run_start"
    assert kinds[-1] == "run_end"

    turns = [e for e in events if e["event"] == "turn"]
    assistant_turns = [t for t in turns if t["role"] == "assistant"]
    tool_turns = [t for t in turns if t["role"] == "tool"]
    # Two delta-chunks before the tool fold into one assistant turn;
    # the second message-chunk after the tool result is a second turn.
    assert len(assistant_turns) == 2
    assert len(tool_turns) == 1

    run_start = events[0]
    assert run_start["task_id"] == "L0_demo"
    assert run_start["model"] == "gemini-3-pro"
    assert run_start["harness"].startswith("gemini-cli@")
    assert run_start["tier"] == "T0"
    # Sensitivity-axis fields populated.
    assert run_start["system_prompt_verbatim"] == _SANDBOX_SYSTEM_PROMPT
    # gemini-3-pro is an alias of gemini-3.1-pro-preview (1,048,576 ctx).
    assert run_start["model_context_window_tokens"] == 1_048_576
    assert run_start["reasoning"]["effort"] is None

    first_assistant = assistant_turns[0]
    # Tool call was attached to the same in-flight assistant turn.
    assert any(tc["name"] == "WriteFile" for tc in first_assistant["tool_calls"])
    # Delta chunks concatenated into one model_output.
    assert "I'll create the file now." in first_assistant["model_output"]

    tool_turn = tool_turns[0]
    assert tool_turn["tool_returns"]
    assert tool_turn["tool_returns"][0]["tool_use_id"] == "tool-call-1"
    assert tool_turn["tool_returns"][0]["is_error"] is False

    run_end = events[-1]
    assert run_end["status"] == "completed"
    # Totals come from the final `result.stats` block.
    assert run_end["totals"]["tokens_in"] == 1200
    assert run_end["totals"]["tokens_out"] == 58
    assert run_end["totals"]["latency_ms"] == 4321
    # Cost was backfilled via the pricing module (Gemini emits no cost).
    # gemini-3-pro alias → gemini-3.1-pro-preview @ $2/$12 per 1M.
    expected_cost = (1200 / 1_000_000) * 2.00 + (58 / 1_000_000) * 12.00
    assert abs(run_end["totals"]["cost_usd"] - expected_cost) < 1e-9

    # Trajectory invariants hold.
    assert validate(traj_path) == []


def test_runner_writes_gemini_md_with_sandbox_preamble(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    workdir = tmp_path / "vault"
    workdir.mkdir()
    _patch_popen(monkeypatch, canned_stream)

    runner = GeminiCLIRunner()
    runner.prepare(None)
    with TrajectoryWriter(tmp_path / "t.jsonl") as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)

    gemini_md = (workdir / "GEMINI.md").read_text(encoding="utf-8")
    assert _SANDBOX_HEADER_MARKER in gemini_md
    assert _SANDBOX_SYSTEM_PROMPT in gemini_md


def test_runner_preserves_existing_gemini_md(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    workdir = tmp_path / "vault"
    workdir.mkdir()
    operator_md = "# Operator config\n\nPreserve me.\n"
    (workdir / "GEMINI.md").write_text(operator_md, encoding="utf-8")

    _patch_popen(monkeypatch, canned_stream)
    runner = GeminiCLIRunner()
    runner.prepare(None)
    with TrajectoryWriter(tmp_path / "t.jsonl") as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)

    final = (workdir / "GEMINI.md").read_text(encoding="utf-8")
    assert _SANDBOX_HEADER_MARKER in final
    assert "# Operator config" in final
    # Sandbox preamble must come BEFORE the operator content.
    assert final.index(_SANDBOX_HEADER_MARKER) < final.index("# Operator config")


def test_scrub_turn_redacts_workdir_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "vault"
    workdir.mkdir()
    workdir_abs = str(workdir.resolve())
    canned = "\n".join(
        [
            json.dumps({
                "type": "init", "timestamp": "t", "session_id": "s", "model": "gemini-3-pro",
            }),
            json.dumps({
                "type": "message", "timestamp": "t", "role": "user", "content": "hi",
            }),
            json.dumps({
                "type": "tool_use", "timestamp": "t", "tool_name": "ReadFile",
                "tool_id": "tc-1",
                "parameters": {"file_path": f"{workdir_abs}/secret.txt"},
            }),
            json.dumps({
                "type": "tool_result", "timestamp": "t", "tool_id": "tc-1",
                "status": "success",
                "output": f"read {workdir_abs}/secret.txt successfully",
            }),
            json.dumps({
                "type": "result", "timestamp": "t", "status": "success",
                "stats": {
                    "total_tokens": 10, "input_tokens": 8, "output_tokens": 2,
                    "duration_ms": 100, "tool_calls": 1,
                },
            }),
        ]
    ) + "\n"
    _patch_popen(monkeypatch, canned)

    traj_path = tmp_path / "t.jsonl"
    runner = GeminiCLIRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    raw = json.dumps(events)
    # Workdir absolute path must not appear anywhere in the recorded
    # trajectory after _scrub_turn.
    assert workdir_abs not in raw
    # The path is rewritten to the `./` relative form.
    assert "./secret.txt" in raw


def test_cost_backfilled_when_stats_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    """Gemini emits 0 cost_usd; the runner must backfill via pricing."""
    workdir = tmp_path / "vault"
    workdir.mkdir()
    _patch_popen(monkeypatch, canned_stream)
    runner = GeminiCLIRunner(model="gemini-3-pro")
    runner.prepare(None)
    with TrajectoryWriter(tmp_path / "t.jsonl") as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)

    events = [
        json.loads(ln) for ln in (tmp_path / "t.jsonl").read_text().splitlines() if ln.strip()
    ]
    run_end = next(e for e in events if e["event"] == "run_end")
    assert run_end["totals"]["cost_usd"] > 0.0


def test_runner_records_vault_diff_when_files_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, canned_stream: str
) -> None:
    traj_path = tmp_path / "trajectory.jsonl"
    workdir = tmp_path / "vault2"
    workdir.mkdir()

    def on_run(argv, kwargs):
        cwd = Path(kwargs["cwd"])
        (cwd / "hello.txt").write_text("hello world\n", encoding="utf-8")

    _patch_popen(monkeypatch, canned_stream, on_run=on_run)

    runner = GeminiCLIRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    assistant_turns = [e for e in events if e["event"] == "turn" and e["role"] == "assistant"]
    last_assistant = assistant_turns[-1]
    assert last_assistant["vault_state_diff"] is not None
    assert "hello.txt" in last_assistant["vault_state_diff"]["created"]


def test_runner_version_falls_back_to_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("no gemini binary in test env")

    monkeypatch.setattr(subprocess, "run", fake_run)
    runner = GeminiCLIRunner()
    assert runner.version() == "gemini-cli@unknown"


def test_runner_version_includes_binary_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _R:
        returncode = 0
        stdout = "0.20.2\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    runner = GeminiCLIRunner()
    assert runner.version() == "gemini-cli@0.20.2"


def test_runner_handles_missing_binary_cleanly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If `gemini` binary isn't installed, runner returns RunStatus.failed."""
    # Pre-cache the version so we don't probe the (now-broken) Popen path
    # for it. Production callers cache version on first probe anyway.
    runner = GeminiCLIRunner()
    runner._cached_version = "gemini-cli@unknown"

    def fake_popen(argv, **kwargs):
        raise FileNotFoundError("no gemini binary")

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    workdir = tmp_path / "vault"
    workdir.mkdir()
    traj_path = tmp_path / "t.jsonl"
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        status = runner.run_task(_make_task(), writer, workdir=workdir)

    assert getattr(status, "value", str(status)) in {"unrunnable", "RunStatus.unrunnable"}
    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]
    kinds = [e["event"] for e in events]
    assert kinds[0] == "run_start"
    assert kinds[-1] == "run_end"
    assert events[-1]["status"] == "unrunnable"


def test_reasoning_effort_kwarg_is_ignored_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="ab_harness.runners.gemini_cli"):
        GeminiCLIRunner(reasoning_effort="high")
    assert any("reasoning_effort" in rec.message for rec in caplog.records)


def test_factory_returns_real_runner_not_stub() -> None:
    """Regression: gemini-cli must no longer be a StubRunner."""
    from ab_harness.runners.factory import StubRunner, make_runner

    runner = make_runner(runner="gemini-cli", model="gemini-3-pro")
    assert isinstance(runner, GeminiCLIRunner)
    assert not isinstance(runner, StubRunner)
    assert runner.name() == "gemini-cli"
