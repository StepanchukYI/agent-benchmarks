"""Unit tests for every assertion kind in `ab_harness.scorers.assertions`.

Each assertion gets a pass-case and a fail-case using synthetic trajectory
events. The integration test at the bottom feeds a real Track B YAML
(L0_604 — "no emoji" rule) through the chain to validate end-to-end shape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from ab_harness.scorers.assertions import _ASSERTION_KINDS, run_assertion_chain

# ---------------------------------------------------------------------------
# Helpers — build synthetic trajectory events.
# ---------------------------------------------------------------------------

def _turn(
    idx: int,
    *,
    role: str = "assistant",
    text: str = "",
    calls: list[dict] | None = None,
    returns: list[dict] | None = None,
) -> dict:
    return {
        "event": "turn",
        "idx": idx,
        "role": role,
        "model_output": text,
        "tool_calls": calls or [],
        "tool_returns": returns or [],
        "vault_state_diff": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "latency_ms": 0,
        "cost_usd": 0.0,
    }


def _events(*turns: dict) -> list[dict]:
    return [{"event": "run_start", "run_id": "r", "task_id": "L0_001"}, *turns, {"event": "run_end", "status": "completed"}]


def _check(kind: str, params: dict, events: list[dict], *, expect: bool, fixture_dir: Path | None = None) -> None:
    v = run_assertion_chain("test_scorer", events, None, fixture_dir, [{"kind": kind, **params}])
    assert isinstance(v.detail, dict)
    assert v.detail["assertions"][0]["ok"] is expect, v.detail["assertions"][0]


# ---------------------------------------------------------------------------
# Final assistant message
# ---------------------------------------------------------------------------

def test_final_assistant_message_equals() -> None:
    events = _events(_turn(0, text="hello world"))
    _check("final_assistant_message_equals", {"expected": "hello world"}, events, expect=True)
    _check("final_assistant_message_equals", {"expected": "nope"}, events, expect=False)


def test_final_assistant_message_equals_with_trim() -> None:
    events = _events(_turn(0, text="hello\n\n"))
    _check("final_assistant_message_equals", {"expected": "hello", "trim_whitespace": True}, events, expect=True)


def test_final_assistant_message_contains_substring() -> None:
    events = _events(_turn(0, text="the answer is 42"))
    _check("final_assistant_message_contains_substring", {"substring": "42"}, events, expect=True)
    _check("final_assistant_message_contains_substring", {"substring": "43"}, events, expect=False)


def test_final_assistant_message_contains_substring_verbatim() -> None:
    events = _events(_turn(0, text="THE FORM"))
    _check("final_assistant_message_contains_substring_verbatim", {"substring": "THE FORM"}, events, expect=True)
    _check("final_assistant_message_contains_substring_verbatim", {"substring": "the form"}, events, expect=False)


def test_final_assistant_message_contains_any() -> None:
    events = _events(_turn(0, text="cannot determine the answer"))
    _check("final_assistant_message_contains_any", {"terms": ["unknown", "cannot determine"]}, events, expect=True)
    _check("final_assistant_message_contains_any", {"terms": ["foo", "bar"]}, events, expect=False)


def test_final_assistant_message_contains_at_least_n_of() -> None:
    events = _events(_turn(0, text="Q4 2025 and Q2 2026 are options"))
    _check("final_assistant_message_contains_at_least_n_of", {"terms": ["Q4 2025", "Q2 2026", "X"], "n": 2}, events, expect=True)
    _check("final_assistant_message_contains_at_least_n_of", {"terms": ["Q4 2025", "X"], "n": 2}, events, expect=False)


def test_final_assistant_message_contains_quoted_span() -> None:
    events = _events(_turn(0, text='He said "the moon is full" yesterday'))
    _check(
        "final_assistant_message_contains_quoted_span",
        {"span": "the moon is full", "quote_chars": ['"', "'"]},
        events,
        expect=True,
    )
    _check(
        "final_assistant_message_contains_quoted_span",
        {"span": "the sun is hot", "quote_chars": ['"']},
        events,
        expect=False,
    )


def test_final_assistant_message_does_not_contain() -> None:
    events = _events(_turn(0, text="clean answer"))
    _check("final_assistant_message_does_not_contain", {"forbidden": ["bad"]}, events, expect=True)
    _check("final_assistant_message_does_not_contain", {"forbidden": ["clean"]}, events, expect=False)


def test_final_assistant_message_does_not_match() -> None:
    events = _events(_turn(0, text="zero percent"))
    _check("final_assistant_message_does_not_match", {"patterns": [r"\d+%"]}, events, expect=True)
    events2 = _events(_turn(0, text="50% chance"))
    _check("final_assistant_message_does_not_match", {"patterns": [r"\d+%"]}, events2, expect=False)


def test_final_assistant_message_matches_any() -> None:
    events = _events(_turn(0, text="dry spring nectar"))
    _check("final_assistant_message_matches_any", {"patterns": ["(?i)dry spring"]}, events, expect=True)
    _check("final_assistant_message_matches_any", {"patterns": ["(?i)snow"]}, events, expect=False)


def test_final_assistant_message_word_count_exact() -> None:
    events = _events(_turn(0, text="one two three four five"))
    _check("final_assistant_message_word_count", {"expected": 5}, events, expect=True)
    _check("final_assistant_message_word_count", {"expected": 7}, events, expect=False)


def test_final_assistant_message_word_count_range() -> None:
    events = _events(_turn(0, text="one two three"))
    _check("final_assistant_message_word_count", {"min": 2, "max": 5}, events, expect=True)
    _check("final_assistant_message_word_count", {"min": 4}, events, expect=False)


def test_final_assistant_message_word_count_min() -> None:
    events = _events(_turn(0, text="one two three"))
    _check("final_assistant_message_word_count_min", {"min": 3}, events, expect=True)
    _check("final_assistant_message_word_count_min", {"min": 10}, events, expect=False)


def test_final_assistant_message_no_emoji() -> None:
    events_clean = _events(_turn(0, text="plain greeting"))
    _check("final_assistant_message_no_emoji", {}, events_clean, expect=True)
    events_dirty = _events(_turn(0, text="happy day 🎉"))
    _check("final_assistant_message_no_emoji", {}, events_dirty, expect=False)


def test_final_assistant_message_no_markdown() -> None:
    events_clean = _events(_turn(0, text="just text"))
    _check("final_assistant_message_no_markdown", {}, events_clean, expect=True)
    events_dirty = _events(_turn(0, text="**bold**"))
    _check("final_assistant_message_no_markdown", {}, events_dirty, expect=False)


def test_final_assistant_message_no_quotes() -> None:
    events_clean = _events(_turn(0, text="no quoted things here"))
    _check("final_assistant_message_no_quotes", {}, events_clean, expect=True)
    events_dirty = _events(_turn(0, text='something "long quoted phrase" inside'))
    _check("final_assistant_message_no_quotes", {}, events_dirty, expect=False)


def test_no_markdown_fence() -> None:
    _check("no_markdown_fence", {}, _events(_turn(0, text="plain")), expect=True)
    _check("no_markdown_fence", {}, _events(_turn(0, text="```json\n{}\n```")), expect=False)


def test_no_prose_surrounding_json() -> None:
    _check("no_prose_surrounding_json", {}, _events(_turn(0, text='{"a": 1}')), expect=True)
    _check("no_prose_surrounding_json", {}, _events(_turn(0, text='Here you go: {"a": 1}')), expect=False)


# ---------------------------------------------------------------------------
# Assistant text (any turn)
# ---------------------------------------------------------------------------

def test_assistant_text_mentions_any() -> None:
    events = _events(_turn(0, text="step 1"), _turn(1, text="confirmation needed"))
    _check("assistant_text_mentions_any", {"terms": ["confirmation"]}, events, expect=True)
    _check("assistant_text_mentions_any", {"terms": ["xyz"]}, events, expect=False)


def test_assistant_text_nonempty() -> None:
    _check("assistant_text_nonempty", {}, _events(_turn(0, text="hi")), expect=True)
    _check("assistant_text_nonempty", {}, _events(_turn(0, text="   ")), expect=False)


# ---------------------------------------------------------------------------
# Turn / tool-call counts
# ---------------------------------------------------------------------------

def test_max_turn_count() -> None:
    events = _events(_turn(0), _turn(1), _turn(2))
    _check("max_turn_count", {"max": 5}, events, expect=True)
    _check("max_turn_count", {"max": 2}, events, expect=False)


def test_tool_call_count_exact() -> None:
    events = _events(_turn(0, calls=[{"name": "Bash", "args": {}}, {"name": "Bash", "args": {}}]))
    _check("tool_call_count", {"tool": "Bash", "expected": 2}, events, expect=True)
    _check("tool_call_count", {"tool": "Bash", "expected": 1}, events, expect=False)


def test_tool_call_count_min_and_max() -> None:
    events = _events(_turn(0, calls=[{"name": "fetch_url", "args": {}}, {"name": "fetch_url", "args": {}}]))
    _check("tool_call_count_min", {"tool": "fetch_url", "min": 1}, events, expect=True)
    _check("tool_call_count_min", {"tool": "fetch_url", "min": 5}, events, expect=False)
    _check("tool_call_count_max", {"tool": "fetch_url", "max": 5}, events, expect=True)
    _check("tool_call_count_max", {"tool": "fetch_url", "max": 1}, events, expect=False)


def test_tool_call_order() -> None:
    events = _events(
        _turn(0, calls=[{"name": "create_order", "args": {}}]),
        _turn(1, calls=[{"name": "send_confirmation_email", "args": {}}]),
    )
    _check("tool_call_order", {"order": ["create_order", "send_confirmation_email"]}, events, expect=True)
    _check("tool_call_order", {"order": ["send_confirmation_email", "create_order"]}, events, expect=False)


def test_tool_call_name_does_not_match() -> None:
    events_clean = _events(_turn(0, calls=[{"name": "Write", "args": {}}]))
    _check("tool_call_name_does_not_match", {"patterns": ["(?i)^(?:rm|delete|remove).*"]}, events_clean, expect=True)
    events_dirty = _events(_turn(0, calls=[{"name": "delete_file", "args": {}}]))
    _check("tool_call_name_does_not_match", {"patterns": ["(?i)^(?:rm|delete|remove).*"]}, events_dirty, expect=False)


# ---------------------------------------------------------------------------
# Tool args
# ---------------------------------------------------------------------------

def test_tool_arg_equal() -> None:
    events = _events(_turn(0, calls=[{"name": "set_priority", "args": {"issue_id": "JIRA-42"}}]))
    _check("tool_arg_equal", {"tool": "set_priority", "arg": "issue_id", "expected": "JIRA-42"}, events, expect=True)
    _check("tool_arg_equal", {"tool": "set_priority", "arg": "issue_id", "expected": "JIRA-99"}, events, expect=False)


def test_tool_args_equal() -> None:
    events = _events(_turn(0, calls=[{"name": "create_user", "args": {"email": "a@x", "age": 30}}]))
    _check("tool_args_equal", {"tool": "create_user", "expected": {"email": "a@x", "age": 30}}, events, expect=True)
    _check("tool_args_equal", {"tool": "create_user", "expected": {"email": "a@x"}}, events, expect=False)


def test_tool_args_match_schema(tmp_path: Path) -> None:
    schema_file = tmp_path / "tools.json"
    schema_file.write_text(
        json.dumps(
            {
                "tools": [
                    {
                        "name": "search_items",
                        "parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
                            "required": ["query"],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    good = _events(_turn(0, calls=[{"name": "search_items", "args": {"query": "red shoes", "limit": 5}}]))
    bad = _events(_turn(0, calls=[{"name": "search_items", "args": {"limit": 5}}]))  # missing required `query`

    v = run_assertion_chain(
        "tool_call_validator",
        good,
        None,
        tmp_path,
        [{"kind": "tool_args_match_schema", "tool": "search_items"}],
        extra_context={"tool_schema_path": "tools.json"},
    )
    assert isinstance(v.detail, dict)
    assert v.detail["assertions"][0]["ok"] is True
    v_bad = run_assertion_chain(
        "tool_call_validator",
        bad,
        None,
        tmp_path,
        [{"kind": "tool_args_match_schema", "tool": "search_items"}],
        extra_context={"tool_schema_path": "tools.json"},
    )
    assert isinstance(v_bad.detail, dict)
    assert v_bad.detail["assertions"][0]["ok"] is False


def test_tool_arg_array_set_equal() -> None:
    events = _events(
        _turn(
            0,
            calls=[
                {
                    "name": "submit_form",
                    "args": {
                        "fields": [
                            {"name": "email", "value": "a@x"},
                            {"name": "age", "value": "30"},
                        ]
                    },
                }
            ],
        )
    )
    _check(
        "tool_arg_array_set_equal",
        {
            "tool": "submit_form",
            "arg": "fields",
            "expected": [
                {"name": "age", "value": "30"},
                {"name": "email", "value": "a@x"},
            ],
        },
        events,
        expect=True,
    )
    _check(
        "tool_arg_array_set_equal",
        {"tool": "submit_form", "arg": "fields", "expected": [{"name": "x", "value": "1"}]},
        events,
        expect=False,
    )


def test_tool_arg_in_set() -> None:
    events = _events(_turn(0, calls=[{"name": "set_priority", "args": {"priority": "high"}}]))
    _check(
        "tool_arg_in_set",
        {"tool": "set_priority", "arg": "priority", "allowed": ["high", "critical"]},
        events,
        expect=True,
    )
    _check(
        "tool_arg_in_set",
        {"tool": "set_priority", "arg": "priority", "allowed": ["low"]},
        events,
        expect=False,
    )


def test_tool_arg_type() -> None:
    events = _events(_turn(0, calls=[{"name": "set_temperature", "args": {"celsius": 22}}]))
    _check(
        "tool_arg_type",
        {"tool": "set_temperature", "arg": "celsius", "expected_type": "number", "forbid_string": True},
        events,
        expect=True,
    )
    events_str = _events(_turn(0, calls=[{"name": "set_temperature", "args": {"celsius": "22"}}]))
    _check(
        "tool_arg_type",
        {"tool": "set_temperature", "arg": "celsius", "expected_type": "number", "forbid_string": True},
        events_str,
        expect=False,
    )


def test_tool_arg_from_prior_return() -> None:
    events = _events(
        _turn(
            0,
            calls=[{"id": "c1", "name": "create_order", "args": {"customer_id": "C-42"}}],
        ),
        _turn(
            1,
            role="tool",
            returns=[{"tool_use_id": "c1", "content": {"order_id": "ORD-7"}}],
        ),
        _turn(
            2,
            calls=[{"id": "c2", "name": "send_confirmation_email", "args": {"order_id": "ORD-7"}}],
        ),
    )
    _check(
        "tool_arg_from_prior_return",
        {
            "tool": "send_confirmation_email",
            "arg": "order_id",
            "source_tool": "create_order",
            "source_field": "order_id",
        },
        events,
        expect=True,
    )
    events_bad = _events(
        _turn(0, calls=[{"id": "c1", "name": "create_order", "args": {}}]),
        _turn(1, role="tool", returns=[{"tool_use_id": "c1", "content": {"order_id": "ORD-7"}}]),
        _turn(2, calls=[{"id": "c2", "name": "send_confirmation_email", "args": {"order_id": "FAKE"}}]),
    )
    _check(
        "tool_arg_from_prior_return",
        {
            "tool": "send_confirmation_email",
            "arg": "order_id",
            "source_tool": "create_order",
            "source_field": "order_id",
        },
        events_bad,
        expect=False,
    )


# ---------------------------------------------------------------------------
# Files read
# ---------------------------------------------------------------------------

def test_first_file_read() -> None:
    events = _events(_turn(0, calls=[{"name": "Read", "args": {"file_path": "CLAUDE.md"}}]))
    _check(
        "first_file_read",
        {"expected_oneof": ["CLAUDE.md", "AGENTS.md"]},
        events,
        expect=True,
    )
    events_bad = _events(_turn(0, calls=[{"name": "Read", "args": {"file_path": "README.md"}}]))
    _check(
        "first_file_read",
        {"expected_oneof": ["CLAUDE.md", "AGENTS.md"]},
        events_bad,
        expect=False,
    )


def test_file_read_before_first_assistant_text() -> None:
    events = _events(
        _turn(0, role="assistant", calls=[{"name": "Read", "args": {"file_path": "CLAUDE.md"}}]),
        _turn(1, role="assistant", text="OK based on rules…"),
    )
    _check(
        "file_read_before_first_assistant_text",
        {"expected_oneof": ["CLAUDE.md"]},
        events,
        expect=True,
    )
    events_bad = _events(
        _turn(0, role="assistant", text="Hi"),
        _turn(1, role="assistant", calls=[{"name": "Read", "args": {"file_path": "CLAUDE.md"}}]),
    )
    _check(
        "file_read_before_first_assistant_text",
        {"expected_oneof": ["CLAUDE.md"]},
        events_bad,
        expect=False,
    )


# ---------------------------------------------------------------------------
# Skills / MCP
# ---------------------------------------------------------------------------

def test_skill_invocation_count_named() -> None:
    events = _events(
        _turn(0, calls=[{"name": "Skill", "args": {"skill": "memory:memory-write"}}]),
    )
    _check(
        "skill_invocation_count",
        {"skill": "memory:memory-write", "min": 1},
        events,
        expect=True,
    )
    _check(
        "skill_invocation_count",
        {"skill": "memory:memory-write", "expected": 0},
        events,
        expect=False,
    )


def test_skill_invocation_count_total() -> None:
    events_empty = _events(_turn(0, text="hi"))
    _check("skill_invocation_count_total", {"expected": 0}, events_empty, expect=True)
    events_one = _events(_turn(0, calls=[{"name": "Skill", "args": {"skill": "memory:memory-write"}}]))
    _check("skill_invocation_count_total", {"expected": 0}, events_one, expect=False)


def test_first_skill_invocation() -> None:
    events = _events(_turn(0, calls=[{"name": "Skill", "args": {"skill": "memory:memory-write"}}]))
    _check("first_skill_invocation", {"expected": "memory:memory-write"}, events, expect=True)
    _check("first_skill_invocation", {"expected": "memory:memory-read"}, events, expect=False)


def test_mcp_call_count_total() -> None:
    events_empty = _events(_turn(0, text="hi"))
    _check("mcp_call_count_total", {"expected": 0}, events_empty, expect=True)
    events_mcp = _events(_turn(0, calls=[{"name": "mcp__obsidian__write", "args": {}}]))
    _check("mcp_call_count_total", {"expected": 0}, events_mcp, expect=False)


# ---------------------------------------------------------------------------
# replay_then_compare_json
# ---------------------------------------------------------------------------

def test_replay_then_compare_json_idempotency() -> None:
    events = _events(
        _turn(
            0,
            calls=[
                {
                    "name": "Write",
                    "args": {"file_path": "state.json", "content": '{"counter": 1, "flag": true}'},
                }
            ],
        )
    )
    _check(
        "replay_then_compare_json",
        {"target": "state.json", "expected_after_double_apply": {"counter": 1, "flag": True}},
        events,
        expect=True,
    )
    events_bad = _events(
        _turn(
            0,
            calls=[
                {
                    "name": "Write",
                    "args": {"file_path": "state.json", "content": '{"counter": 2, "flag": true}'},
                }
            ],
        )
    )
    _check(
        "replay_then_compare_json",
        {"target": "state.json", "expected_after_double_apply": {"counter": 1, "flag": True}},
        events_bad,
        expect=False,
    )


def test_replay_then_compare_json_fixture(tmp_path: Path) -> None:
    (tmp_path / "expected.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    events = _events(_turn(0, text='{"a": 1}'))
    v = run_assertion_chain(
        "json_only_check",
        events,
        None,
        tmp_path,
        [{"kind": "replay_then_compare_json", "expected_path": "expected.json"}],
    )
    assert isinstance(v.detail, dict)
    assert v.detail["assertions"][0]["ok"] is True


# ---------------------------------------------------------------------------
# Workdir file-state assertions (L0_009/L0_010/L0_012 batch)
# ---------------------------------------------------------------------------


def _wfile_v(tmp_path, kind: str, params: dict[str, Any]) -> tuple[bool, dict]:
    """Run a single workdir_file_* assertion against tmp_path and return
    (ok, detail) — same shape the chain runner exposes."""
    v = run_assertion_chain("x", _events(_turn(0)), tmp_path, None, [dict(params, kind=kind)])
    return v.detail["assertions"][0]["ok"], v.detail["assertions"][0]["detail"]


def test_workdir_file_exists_pass(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    ok, _ = _wfile_v(tmp_path, "workdir_file_exists", {"path": "a.txt"})
    assert ok


def test_workdir_file_exists_fail(tmp_path: Path) -> None:
    ok, _ = _wfile_v(tmp_path, "workdir_file_exists", {"path": "missing.txt"})
    assert not ok


def test_workdir_file_absent_pass(tmp_path: Path) -> None:
    ok, _ = _wfile_v(tmp_path, "workdir_file_absent", {"path": "missing.txt"})
    assert ok


def test_workdir_file_absent_fail(tmp_path: Path) -> None:
    (tmp_path / "still-here.txt").write_text("x", encoding="utf-8")
    ok, _ = _wfile_v(tmp_path, "workdir_file_absent", {"path": "still-here.txt"})
    assert not ok


def test_workdir_file_content_equals_pass(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hello", encoding="utf-8")
    ok, _ = _wfile_v(tmp_path, "workdir_file_content_equals", {"path": "f.txt", "content": "hello"})
    assert ok


def test_workdir_file_content_equals_fail(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("world", encoding="utf-8")
    ok, _ = _wfile_v(tmp_path, "workdir_file_content_equals", {"path": "f.txt", "content": "hello"})
    assert not ok


def test_workdir_file_bytes_equal_pass(tmp_path: Path) -> None:
    (tmp_path / "b.bin").write_bytes(b"hello")
    ok, _ = _wfile_v(tmp_path, "workdir_file_bytes_equal", {"path": "b.bin", "content": "hello"})
    assert ok


def test_workdir_file_bytes_equal_fail(tmp_path: Path) -> None:
    (tmp_path / "b.bin").write_bytes(b"hello world")
    ok, _ = _wfile_v(tmp_path, "workdir_file_bytes_equal", {"path": "b.bin", "content": "hello"})
    assert not ok


def test_workdir_file_no_bom_pass(tmp_path: Path) -> None:
    (tmp_path / "clean.txt").write_text("no bom here", encoding="utf-8")
    ok, _ = _wfile_v(tmp_path, "workdir_file_no_bom", {"path": "clean.txt"})
    assert ok


def test_workdir_file_no_bom_fail(tmp_path: Path) -> None:
    (tmp_path / "withbom.txt").write_bytes(b"\xef\xbb\xbfHello")
    ok, _ = _wfile_v(tmp_path, "workdir_file_no_bom", {"path": "withbom.txt"})
    assert not ok


def test_workdir_file_no_crlf_pass(tmp_path: Path) -> None:
    (tmp_path / "lf.txt").write_bytes(b"line1\nline2\n")
    ok, _ = _wfile_v(tmp_path, "workdir_file_no_crlf", {"path": "lf.txt"})
    assert ok


def test_workdir_file_no_crlf_fail(tmp_path: Path) -> None:
    (tmp_path / "crlf.txt").write_bytes(b"line1\r\nline2\r\n")
    ok, _ = _wfile_v(tmp_path, "workdir_file_no_crlf", {"path": "crlf.txt"})
    assert not ok


def test_workdir_file_preserves_crlf_pass(tmp_path: Path) -> None:
    (tmp_path / "ini.txt").write_bytes(b"[s]\r\nk=v\r\n")
    ok, _ = _wfile_v(tmp_path, "workdir_file_preserves_crlf", {"path": "ini.txt"})
    assert ok


def test_workdir_file_preserves_crlf_fail(tmp_path: Path) -> None:
    (tmp_path / "lf.txt").write_bytes(b"line1\nline2\n")
    ok, _ = _wfile_v(tmp_path, "workdir_file_preserves_crlf", {"path": "lf.txt"})
    assert not ok


def test_workdir_file_encoding_utf8_pass(tmp_path: Path) -> None:
    (tmp_path / "u.txt").write_text("Привет, мир. 🌍", encoding="utf-8")
    ok, _ = _wfile_v(tmp_path, "workdir_file_encoding_utf8", {"path": "u.txt"})
    assert ok


def test_workdir_file_encoding_utf8_fail(tmp_path: Path) -> None:
    # Invalid UTF-8 byte sequence (lone 0xFF).
    (tmp_path / "bad.bin").write_bytes(b"\xff\xfeabc")
    ok, _ = _wfile_v(tmp_path, "workdir_file_encoding_utf8", {"path": "bad.bin"})
    assert not ok


# ---------------------------------------------------------------------------
# Chain runner — pass/fail counts, unknown-kind handling
# ---------------------------------------------------------------------------

def test_unknown_kind_reports_error() -> None:
    v = run_assertion_chain("x", _events(_turn(0)), None, None, [{"kind": "nonexistent_kind"}])
    assert isinstance(v.detail, dict)
    assert v.detail["assertions"][0]["ok"] is False
    assert "unknown" in v.detail["assertions"][0]["detail"]["error"]


def test_all_assertion_kinds_have_at_least_one_passing_test() -> None:
    # Sanity floor: every kind registered in _ASSERTION_KINDS should appear in
    # at least one of the tests above. We compute it by inspecting the test
    # module source for `_check("<kind>"` literals.
    test_path = Path(__file__).read_text(encoding="utf-8")
    missing = [k for k in _ASSERTION_KINDS if f'"{k}"' not in test_path and f"'{k}'" not in test_path]
    assert not missing, f"missing tests for kinds: {missing}"


# ---------------------------------------------------------------------------
# Integration — real L0_604 YAML
# ---------------------------------------------------------------------------

DATASETS_ROOT = (
    Path(__file__).resolve().parents[3] / "packages" / "ab-datasets" / "ab_datasets"
)


@pytest.mark.skipif(not (DATASETS_ROOT / "L0_foundation" / "L0_604-respect-negative-user-rule-no-emoji.yaml").exists(), reason="dataset YAML not present")
def test_integration_l0_604_emoji_yaml_chain() -> None:
    """Load L0_604, build a trajectory containing an emoji, run the chain.

    The `no_emoji_check` scorer should fail because the final message contains
    🎉. We pull the assertions list straight from the YAML to make sure we are
    consuming the exact param shapes Track B authors with.
    """
    yaml_path = DATASETS_ROOT / "L0_foundation" / "L0_604-respect-negative-user-rule-no-emoji.yaml"
    data: dict[str, Any] = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    scorer_specs = data["scorer_chain"]
    no_emoji_spec = next(s for s in scorer_specs if s["name"] == "no_emoji_check")
    assertions = no_emoji_spec["config"]["assertions"]

    events = _events(_turn(0, text="Sure thing! 🎉"))
    v = run_assertion_chain("no_emoji_check", events, None, None, assertions)
    assert v.pass_ is False
    assert isinstance(v.detail, dict)
    flagged = [a for a in v.detail["assertions"] if a["kind"] == "final_assistant_message_no_emoji"]
    assert flagged and flagged[0]["ok"] is False
