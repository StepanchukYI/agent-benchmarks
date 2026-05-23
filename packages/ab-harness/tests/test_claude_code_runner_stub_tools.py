"""ClaudeCodeRunner: stub MCP tool exposure via tools.json in the workdir.

When a task's workdir contains a tools.json, the runner must:
1. Write an mcp_config.json that registers the stub MCP server.
2. Pass --strict-mcp-config --mcp-config <that file> so the agent can call
   the declared tools.
3. Normalise the tool_use / tool_result stream-json events into trajectory
   tool_calls / tool_returns pairs so tool_call_validator can score them.
"""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any, ClassVar

import pytest
from ab_harness.runners.claude_code import ClaudeCodeRunner, _build_stub_mcp_config
from ab_harness.trajectory.validate import validate
from ab_harness.trajectory.writer import TrajectoryWriter

# ---------------------------------------------------------------------------
# Canned stream-json fixture: agent calls search_items then summarises.
# ---------------------------------------------------------------------------
_STUB_TOOL_STREAM = "\n".join([
    json.dumps({
        "type": "system",
        "subtype": "init",
        "session_id": "sess-stub",
        "model": "claude-sonnet-4-5",
        "cwd": "/work",
        "tools": ["search_items"],
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "id": "msg_s1",
            "role": "assistant",
            "model": "claude-sonnet-4-5",
            "content": [
                {"type": "text", "text": "I will search for items."},
                {
                    "type": "tool_use",
                    "id": "toolu_s1",
                    "name": "search_items",
                    "input": {"query": "widget", "limit": 5},
                },
            ],
            "usage": {"input_tokens": 800, "output_tokens": 30},
        },
        "session_id": "sess-stub",
    }),
    json.dumps({
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_s1",
                    "content": [{"type": "text", "text": '{"status":"ok","result":null}'}],
                    "is_error": False,
                }
            ],
        },
        "session_id": "sess-stub",
    }),
    json.dumps({
        "type": "assistant",
        "message": {
            "id": "msg_s2",
            "role": "assistant",
            "model": "claude-sonnet-4-5",
            "content": [{"type": "text", "text": "Search complete."}],
            "usage": {"input_tokens": 900, "output_tokens": 12},
        },
        "session_id": "sess-stub",
    }),
    json.dumps({
        "type": "result",
        "subtype": "success",
        "duration_ms": 2100,
        "duration_api_ms": 1900,
        "is_error": False,
        "num_turns": 2,
        "result": "Search complete.",
        "session_id": "sess-stub",
        "total_cost_usd": 0.007,
        "usage": {"input_tokens": 1700, "output_tokens": 42},
    }),
]) + "\n"


class _FakeProc:
    """Minimal Popen stand-in replaying a canned stream."""

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
        pass

    def communicate(self, input=None, timeout=None):
        return self.stdout.getvalue(), self.stderr.getvalue()

    def __enter__(self):
        return self

    def __exit__(self, *_) -> None:
        pass


def _make_task(task_id: str = "L0_301") -> Any:
    class _Task:
        id: ClassVar[str] = task_id
        description: ClassVar[str] = "Search for items with query='widget', limit=5."
        acceptance_criteria: ClassVar[list[str]] = [
            "Exactly one call to search_items is issued.",
            "Args include query='widget' and limit=5.",
        ]

    return _Task()


def _patch_popen(monkeypatch: pytest.MonkeyPatch, stdout_text: str, on_run=None) -> None:
    def fake_popen(argv, **kwargs):
        if "--version" in argv:
            return _FakeProc("1.2.3\n", args=argv)
        if on_run is not None:
            on_run(argv, kwargs)
        return _FakeProc(stdout_text, args=argv)

    monkeypatch.setattr(subprocess, "Popen", fake_popen)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_stub_mcp_config_built_from_tools_json(tmp_path: Path) -> None:
    """_build_stub_mcp_config returns valid JSON with the stub server entry."""
    tools_json = tmp_path / "tools.json"
    tools_json.write_text(
        json.dumps({"tools": [{"name": "search_items", "description": "search"}]}),
        encoding="utf-8",
    )
    cfg_str = _build_stub_mcp_config(str(tools_json))
    cfg = json.loads(cfg_str)
    assert "mcpServers" in cfg
    assert "ab-stub" in cfg["mcpServers"]
    server = cfg["mcpServers"]["ab-stub"]
    assert "command" in server
    assert str(tools_json) in server["args"]


def test_runner_uses_stub_mcp_when_tools_json_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When tools.json exists in workdir, --mcp-config points at the stub server config."""
    workdir = tmp_path / "wd"
    workdir.mkdir()
    (workdir / "tools.json").write_text(
        json.dumps({
            "tools": [
                {
                    "name": "search_items",
                    "description": "Search items by query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                }
            ]
        }),
        encoding="utf-8",
    )
    traj_path = tmp_path / "trajectory.jsonl"

    # Read the mcp config during the Popen call — before cleanup() removes the tempdir.
    captured: dict = {}

    def on_run(argv, kwargs):
        captured["argv"] = list(argv)
        if "--mcp-config" in argv:
            idx = argv.index("--mcp-config")
            mcp_path = Path(argv[idx + 1])
            if mcp_path.exists():
                captured["mcp_cfg"] = json.loads(mcp_path.read_text(encoding="utf-8"))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _patch_popen(monkeypatch, _STUB_TOOL_STREAM, on_run=on_run)

    runner = ClaudeCodeRunner(model="claude-sonnet-4-5")
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    assert "argv" in captured, "Popen was never called"
    argv = captured["argv"]

    # --strict-mcp-config must be present
    assert "--strict-mcp-config" in argv, f"--strict-mcp-config missing from argv: {argv}"

    # The mcp-config must have been readable and contain the stub server
    cfg = captured.get("mcp_cfg")
    assert cfg is not None, "mcp config file was missing or unreadable at Popen time"
    assert "ab-stub" in cfg.get("mcpServers", {}), (
        f"ab-stub server not in mcp config: {cfg}"
    )
    # The stub server args must include the tools.json path
    stub_args = cfg["mcpServers"]["ab-stub"]["args"]
    assert any("tools.json" in a for a in stub_args), (
        f"tools.json path not found in stub server args: {stub_args}"
    )


def test_runner_uses_empty_mcp_when_no_tools_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without tools.json, the mcp config is empty (no stub server registered)."""
    smoke = Path(__file__).parent / "fixtures" / "claude_code_stream_smoke.jsonl"
    canned = smoke.read_text(encoding="utf-8")

    workdir = tmp_path / "wd2"
    workdir.mkdir()
    traj_path = tmp_path / "t2.jsonl"

    # Read the mcp config during the Popen call — before cleanup() removes the tempdir.
    captured: dict = {}

    def on_run(argv, kwargs):
        captured["argv"] = list(argv)
        if "--mcp-config" in argv:
            idx = argv.index("--mcp-config")
            mcp_path = Path(argv[idx + 1])
            if mcp_path.exists():
                captured["mcp_cfg"] = json.loads(mcp_path.read_text(encoding="utf-8"))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _patch_popen(monkeypatch, canned, on_run=on_run)

    runner = ClaudeCodeRunner()
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task("L0_001"), writer, workdir=workdir)
    runner.cleanup()

    cfg = captured.get("mcp_cfg")
    assert cfg is not None, "mcp config file was missing or unreadable at Popen time"
    assert cfg.get("mcpServers") == {}, (
        f"expected empty mcpServers without tools.json, got: {cfg}"
    )


def test_stub_tool_call_lands_in_trajectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tool calls to stub tools are captured in trajectory as tool_calls/tool_returns."""
    workdir = tmp_path / "wd3"
    workdir.mkdir()
    (workdir / "tools.json").write_text(
        json.dumps({
            "tools": [
                {
                    "name": "search_items",
                    "description": "Search items by query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer"},
                        },
                        "required": ["query"],
                    },
                }
            ]
        }),
        encoding="utf-8",
    )
    traj_path = tmp_path / "t3.jsonl"

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _patch_popen(monkeypatch, _STUB_TOOL_STREAM)

    runner = ClaudeCodeRunner(model="claude-sonnet-4-5")
    runner.prepare(None)
    with TrajectoryWriter(traj_path) as writer:
        runner.run_task(_make_task(), writer, workdir=workdir)
    runner.cleanup()

    events = [json.loads(ln) for ln in traj_path.read_text().splitlines() if ln.strip()]

    # Trajectory must be valid
    errors = validate(traj_path)
    assert errors == [], f"Trajectory validation errors: {errors}"

    # Find the assistant turn that carries the tool call
    tool_call_turns = [
        e for e in events
        if e.get("event") == "turn"
        and e.get("role") == "assistant"
        and any(tc.get("name") == "search_items" for tc in (e.get("tool_calls") or []))
    ]
    assert tool_call_turns, (
        "No assistant turn with tool_call name='search_items' found in trajectory.\n"
        + json.dumps(events, indent=2)
    )

    tc = next(
        tc for tc in tool_call_turns[0]["tool_calls"] if tc["name"] == "search_items"
    )
    assert tc["args"].get("query") == "widget", f"Expected query='widget', got: {tc['args']}"
    assert tc["args"].get("limit") == 5, f"Expected limit=5, got: {tc['args']}"

    # The corresponding tool_return turn must also be present
    tool_return_turns = [
        e for e in events
        if e.get("event") == "turn"
        and e.get("role") == "tool"
        and any(
            tr.get("tool_use_id") == "toolu_s1"
            for tr in (e.get("tool_returns") or [])
        )
    ]
    assert tool_return_turns, (
        "No tool-return turn for tool_use_id='toolu_s1' found in trajectory."
    )

    tr = next(
        tr for tr in tool_return_turns[0]["tool_returns"]
        if tr.get("tool_use_id") == "toolu_s1"
    )
    assert not tr.get("is_error"), f"Expected is_error=False, got: {tr}"
