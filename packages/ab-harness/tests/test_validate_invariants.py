"""Table-driven invariant checks for trajectory.validate()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ab_harness.trajectory.validate import validate


def _write_jsonl(path: Path, events: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _good_run_start() -> dict:
    return {
        "event": "run_start",
        "run_id": "r1",
        "task_id": "L0_001",
        "model": "claude-sonnet-4-5",
        "harness": "claude-code-cli@unknown",
        "tier": "T0",
        "tier_hash": None,
        "dataset_version": "ab-datasets==0.0.1",
        "prompt_template_hash": None,
        "started_at": "2026-05-21T12:00:00Z",
    }


def _good_turn(idx: int, role: str = "assistant") -> dict:
    return {
        "event": "turn",
        "idx": idx,
        "role": role,
        "prompt_delta": None,
        "tool_calls": [],
        "tool_returns": [],
        "model_output": "",
        "vault_state_diff": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "latency_ms": 0,
        "cost_usd": 0.0,
    }


def _good_run_end(status: str = "completed") -> dict:
    return {
        "event": "run_end",
        "finished_at": "2026-05-21T12:00:14Z",
        "status": status,
        "totals": {
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
            "score": 1.0,
        },
    }


def _good_scorer(name: str = "schema_validator") -> dict:
    return {
        "event": "scorer",
        "scorer": name,
        "kind": "deterministic",
        "pass": True,
        "score": 1.0,
        "detail": "ok",
    }


def test_happy_path_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "good.jsonl"
    _write_jsonl(
        path,
        [
            _good_run_start(),
            _good_turn(0, "user"),
            _good_turn(1, "assistant"),
            _good_scorer("schema_validator"),
            _good_run_end(),
        ],
    )
    assert validate(path) == []


def test_invariant_one_run_start(tmp_path: Path) -> None:
    path = tmp_path / "two_starts.jsonl"
    _write_jsonl(
        path,
        [
            _good_run_start(),
            _good_run_start(),
            _good_turn(0),
            _good_run_end(),
        ],
    )
    issues = validate(path)
    assert any("run_start" in i for i in issues)


def test_invariant_one_run_end_first_last(tmp_path: Path) -> None:
    path = tmp_path / "end_not_last.jsonl"
    _write_jsonl(
        path,
        [
            _good_run_start(),
            _good_run_end(),
            _good_turn(0),
        ],
    )
    issues = validate(path)
    assert any("run_end must be the last" in i for i in issues)


def test_invariant_run_end_status(tmp_path: Path) -> None:
    path = tmp_path / "bad_status.jsonl"
    _write_jsonl(
        path,
        [
            _good_run_start(),
            _good_turn(0),
            _good_run_end(status="bogus"),
        ],
    )
    issues = validate(path)
    assert any("status invalid" in i for i in issues)


def test_invariant_turn_idx_monotonic(tmp_path: Path) -> None:
    path = tmp_path / "bad_idx.jsonl"
    _write_jsonl(
        path,
        [
            _good_run_start(),
            _good_turn(0),
            _good_turn(2),
            _good_run_end(),
        ],
    )
    issues = validate(path)
    assert any("monotonic" in i for i in issues)


def test_invariant_turn_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "bad_turn.jsonl"
    broken = _good_turn(0)
    del broken["tokens_in"]
    broken["tool_calls"] = None  # also wrong type
    _write_jsonl(
        path,
        [
            _good_run_start(),
            broken,
            _good_run_end(),
        ],
    )
    issues = validate(path)
    assert any("tool_calls must be a list" in i for i in issues)
    assert any("missing required field 'tokens_in'" in i for i in issues)


def test_invariant_scorers_after_last_turn(tmp_path: Path) -> None:
    path = tmp_path / "early_scorer.jsonl"
    _write_jsonl(
        path,
        [
            _good_run_start(),
            _good_turn(0),
            _good_scorer(),
            _good_turn(1),
            _good_run_end(),
        ],
    )
    issues = validate(path)
    assert any("before/at final turn" in i for i in issues)


def test_invariant_scorer_chain_order(tmp_path: Path) -> None:
    path = tmp_path / "chain_order.jsonl"
    _write_jsonl(
        path,
        [
            _good_run_start(),
            _good_turn(0),
            _good_scorer("b_check"),
            _good_scorer("a_check"),
            _good_run_end(),
        ],
    )

    class _Spec:
        def __init__(self, name: str) -> None:
            self.name = name

    chain = [_Spec("a_check"), _Spec("b_check")]
    issues = validate(path, scorer_chain=chain)
    assert any("scorer order mismatch" in i for i in issues)


def test_invariant_scorer_chain_order_matches(tmp_path: Path) -> None:
    path = tmp_path / "chain_ok.jsonl"
    _write_jsonl(
        path,
        [
            _good_run_start(),
            _good_turn(0),
            _good_scorer("a_check"),
            _good_scorer("b_check"),
            _good_run_end(),
        ],
    )

    chain = [{"name": "a_check"}, {"name": "b_check"}]
    issues = validate(path, scorer_chain=chain)
    assert issues == []


@pytest.mark.parametrize(
    "removed",
    ["tokens_in", "tokens_out", "latency_ms", "cost_usd"],
)
def test_invariant_all_required_turn_fields_individually(tmp_path: Path, removed: str) -> None:
    path = tmp_path / f"missing_{removed}.jsonl"
    bad = _good_turn(0)
    del bad[removed]
    _write_jsonl(
        path,
        [
            _good_run_start(),
            bad,
            _good_run_end(),
        ],
    )
    issues = validate(path)
    assert any(removed in i for i in issues)
