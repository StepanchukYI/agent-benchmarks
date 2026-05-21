"""Extended schema_scorer modes: json_value_equals + final_assistant_message.

Pin Track B's new YAML shapes against the scorer impl. Failures here
mean a benchmark task YAML is referencing a config the harness doesn't
support — which manifests as 0.575-floor false-fails.
"""

from __future__ import annotations

import json
from pathlib import Path

from ab_harness.scorers.schema import schema_scorer


def _write_trajectory(
    path: Path,
    *,
    final_assistant: str | None = None,
    tool_writes: list[tuple[str, str]] | None = None,
) -> None:
    """Minimal trajectory: run_start + N turns + run_end."""
    lines = [{"event": "run_start", "task_id": "T", "model": "m"}]
    idx = 0
    for p, content in tool_writes or []:
        lines.append(
            {
                "event": "turn",
                "idx": idx,
                "role": "tool",
                "tool_returns": [{"path": p, "content": content}],
            }
        )
        idx += 1
    if final_assistant is not None:
        lines.append(
            {
                "event": "turn",
                "idx": idx,
                "role": "assistant",
                "model_output": final_assistant,
                "tool_calls": [],
                "tool_returns": [],
            }
        )
    lines.append({"event": "run_end"})
    path.write_text("\n".join(json.dumps(d) for d in lines), encoding="utf-8")


def test_json_value_equals_passes_on_deep_equal(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(
        json.dumps({"counter": 1, "flag": True}), encoding="utf-8"
    )
    v = schema_scorer(
        workdir=tmp_path,
        mode="json_value_equals",
        target="state.json",
        expected={"counter": 1, "flag": True},
        additional_properties_forbidden=True,
    )
    assert v.pass_ is True
    assert v.score == 1.0


def test_json_value_equals_fails_on_value_mismatch(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(
        json.dumps({"counter": 2, "flag": True}), encoding="utf-8"
    )
    v = schema_scorer(
        workdir=tmp_path,
        mode="json_value_equals",
        target="state.json",
        expected={"counter": 1, "flag": True},
    )
    assert v.pass_ is False
    assert any(m["key"] == "counter" for m in v.detail["mismatches"])


def test_json_value_equals_fails_on_extra_key_when_forbidden(tmp_path: Path) -> None:
    (tmp_path / "state.json").write_text(
        json.dumps({"counter": 1, "flag": True, "extra": "x"}), encoding="utf-8"
    )
    v = schema_scorer(
        workdir=tmp_path,
        mode="json_value_equals",
        target="state.json",
        expected={"counter": 1, "flag": True},
        additional_properties_forbidden=True,
    )
    assert v.pass_ is False
    assert "extra" in v.detail.get("extra_keys", [])


def test_json_value_equals_allows_extra_key_by_default(tmp_path: Path) -> None:
    """Default (additional_properties_forbidden=False) treats == structurally.

    A dict with extra keys is NOT equal to a smaller dict under Python ==,
    so we still fail — but with a value-mismatch detail, not a key-set
    one. This documents the expected behavior so YAML authors know to
    set ``additional_properties_forbidden: true`` if they want strict
    key matching.
    """
    (tmp_path / "state.json").write_text(
        json.dumps({"counter": 1, "flag": True, "extra": "x"}), encoding="utf-8"
    )
    v = schema_scorer(
        workdir=tmp_path,
        mode="json_value_equals",
        target="state.json",
        expected={"counter": 1, "flag": True},
    )
    assert v.pass_ is False
    # Without strict-key enforcement, this falls through to the
    # value-mismatch path (dicts differ structurally).


def test_final_assistant_message_passes_schema(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_trajectory(
        traj,
        final_assistant=json.dumps({"name": "Paris", "country": "France", "population": 2102650}),
    )
    v = schema_scorer(
        trajectory_path=traj,
        mode="exact_json",
        input="final_assistant_message",
        schema={
            "type": "object",
            "required": ["name", "country", "population"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "const": "Paris"},
                "country": {"type": "string", "const": "France"},
                "population": {"type": "integer", "minimum": 2_000_000, "maximum": 3_000_000},
            },
        },
    )
    assert v.pass_ is True
    assert v.score == 1.0


def test_final_assistant_message_strips_code_fence(tmp_path: Path) -> None:
    """Models often emit JSON inside ```json fences even when told not to.

    Scorer should still parse them — otherwise we'd ding the model for
    formatting rather than the actual schema mismatch.
    """
    traj = tmp_path / "trajectory.jsonl"
    fenced = '```json\n{"name": "Paris", "country": "France", "population": 2102650}\n```'
    _write_trajectory(traj, final_assistant=fenced)
    v = schema_scorer(
        trajectory_path=traj,
        mode="exact_json",
        input="final_assistant_message",
        schema={
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string", "const": "Paris"}},
        },
    )
    assert v.pass_ is True, v.detail


def test_final_assistant_message_fails_on_extra_key(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_trajectory(
        traj,
        final_assistant=json.dumps({"name": "Paris", "country": "France", "population": 2102650, "extra": True}),
    )
    v = schema_scorer(
        trajectory_path=traj,
        mode="exact_json",
        input="final_assistant_message",
        schema={
            "type": "object",
            "required": ["name", "country", "population"],
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "const": "Paris"},
                "country": {"type": "string", "const": "France"},
                "population": {"type": "integer"},
            },
        },
    )
    assert v.pass_ is False
    assert v.detail["total_errors"] >= 1


def test_final_assistant_message_no_messages(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_trajectory(traj, final_assistant=None)
    v = schema_scorer(
        trajectory_path=traj,
        mode="exact_json",
        input="final_assistant_message",
        schema={"type": "object"},
    )
    assert v.pass_ is False
    assert "no assistant model_output" in v.detail.get("error", "")


def test_schema_mode_alias_exact_json_works(tmp_path: Path) -> None:
    """exact_json and schema and jsonschema all map to the same dispatch."""
    (tmp_path / "out.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "integer"}}}
    for alias in ("schema", "exact_json", "jsonschema"):
        v = schema_scorer(workdir=tmp_path, mode=alias, target="out.json", schema=schema)
        assert v.pass_ is True, alias


def test_legacy_execution_mode_replay_still_works(tmp_path: Path) -> None:
    """Backward compat: mode='replay' (harness signal) still routes through
    the schema path with default comparison mode."""
    traj = tmp_path / "trajectory.jsonl"
    _write_trajectory(traj, tool_writes=[("out.json", json.dumps({"x": 5}))])
    v = schema_scorer(
        trajectory_path=traj,
        mode="replay",
        target="out.json",
        schema={"type": "object", "required": ["x"]},
    )
    assert v.pass_ is True


def test_runner_does_not_clobber_yaml_mode() -> None:
    """Runner uses setdefault('mode', ...) so YAML's mode stays intact."""
    # Smoke: import-level check; full pipeline tested via test_scorer_runner.py
    # (the setdefault change is exercised indirectly through every Track B
    # task that sets ``mode: json_value_equals``).
    import inspect

    from ab_harness.scorers import runner
    from ab_harness.scorers.runner import run_scorer_chain  # noqa: F401

    src = inspect.getsource(runner)
    assert 'kwargs.setdefault("mode"' in src, (
        "runner.py must use setdefault so YAML's mode survives. If you "
        "see kwargs['mode'] = ... unconditional assignment, that's a "
        "regression — Track B's `mode: json_value_equals` will be "
        "clobbered to 'run' / 'replay' and the scorer falls back to the "
        "default schema validation path."
    )
