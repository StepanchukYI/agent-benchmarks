"""LLM-judge real impl — covers prompt assembly, client, scorer, VCR cache.

All tests must run WITHOUT network. Live mode is opt-in via AB_LLM_JUDGE_LIVE=1
and is exercised manually, not in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ab_harness.judge import build_judge_prompt
from ab_harness.judge.client import (
    JudgeClient,
    JudgeError,
    _extract_assistant_text,
    _parse_judge_output,
    _prompt_key,
    judge_call,
)
from ab_harness.judge.prompts import (
    DEFAULT_RUBRIC,
    OUTPUT_SCHEMA,
    summarize_trajectory_for_judge,
)
from ab_harness.scorers.llm_judge import llm_judge_scorer


def _task(**overrides: Any) -> Any:
    base = {
        "id": "L0_001",
        "description": "Create notes/greeting.txt with exact content `Hello, Example.\\n`",
        "acceptance_criteria": [
            "File exists at notes/greeting.txt",
            "Bytes equal Hello, Example.\\n exactly",
        ],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _events_for_l0_001() -> list[dict[str, Any]]:
    return [
        {
            "event": "run_start",
            "run_id": "r1",
            "task_id": "L0_001",
            "model": "claude-sonnet-4-5",
            "tier": "T0",
        },
        {
            "event": "turn",
            "idx": 0,
            "role": "assistant",
            "tool_calls": [
                {
                    "name": "Write",
                    "args": {
                        "file_path": "./notes/greeting.txt",
                        "content": "Hello, Example.\n",
                    },
                }
            ],
            "tool_returns": [],
            "model_output": "Wrote file.",
            "tokens_in": 50,
            "tokens_out": 10,
            "latency_ms": 1200,
        },
        {
            "event": "run_end",
            "status": "completed",
            "totals": {"tokens_in": 50, "tokens_out": 10, "latency_ms": 1200},
        },
    ]


def _write_trajectory(tmp_path: Path, events: list[dict[str, Any]]) -> Path:
    traj = tmp_path / "trajectory.jsonl"
    traj.write_text(
        "".join(json.dumps(e) + "\n" for e in events),
        encoding="utf-8",
    )
    return traj


def _make_cache_record(
    cache_dir: Path,
    model: str,
    prompt: str,
    *,
    score: float = 0.95,
    pass_: bool = True,
    reasoning: str = "matches all criteria",
) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _prompt_key(model, prompt)
    record = {
        "model": model,
        "prompt_sha256": key,
        "request": {"prompt_len": len(prompt)},
        "response": {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"score": score, "pass": pass_, "reasoning": reasoning}
                    ),
                }
            ],
            "model": model,
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 200, "output_tokens": 30},
        },
        "recorded_at": "2026-05-21T12:00:00Z",
    }
    path = cache_dir / f"{key}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# prompt assembly
# ---------------------------------------------------------------------------

def test_build_judge_prompt_uses_default_rubric() -> None:
    prompt = build_judge_prompt(_task(), {"totals": {"turns": 1}})
    assert DEFAULT_RUBRIC in prompt
    assert OUTPUT_SCHEMA in prompt
    assert "L0_001" in prompt


def test_build_judge_prompt_uses_override_rubric() -> None:
    custom = "Be very harsh."
    prompt = build_judge_prompt(_task(), {"totals": {"turns": 1}}, rubric=custom)
    assert custom in prompt
    assert DEFAULT_RUBRIC not in prompt


def test_summarize_trajectory_caps_model_output() -> None:
    big = "a" * 5000
    events = [
        {"event": "run_start", "run_id": "r1"},
        {"event": "turn", "idx": 0, "model_output": big},
        {"event": "run_end", "status": "done"},
    ]
    summary = summarize_trajectory_for_judge(events, model_output_limit=200)
    assert len(summary["final_output"]) <= 300  # truncation + marker line
    assert "truncated" in summary["final_output"]


def test_summarize_trajectory_caps_tool_calls() -> None:
    events: list[dict[str, Any]] = [{"event": "run_start"}]
    for i in range(50):
        events.append(
            {
                "event": "turn",
                "idx": i,
                "tool_calls": [{"name": f"tool_{i}", "args": {"k": "v"}}],
            }
        )
    events.append({"event": "run_end"})
    summary = summarize_trajectory_for_judge(events, tool_call_limit=10)
    assert len(summary["tool_calls"]) == 10
    assert summary["tool_calls_truncated"] is True
    assert summary["totals"]["tool_calls"] == 50


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------

def test_parse_judge_output_plain_json() -> None:
    score, pass_, reasoning = _parse_judge_output(
        '{"score": 0.85, "pass": true, "reasoning": "good"}'
    )
    assert score == 0.85
    assert pass_ is True
    assert reasoning == "good"


def test_parse_judge_output_strips_code_fence() -> None:
    raw = "```json\n" '{"score": 0.5, "pass": false, "reasoning": "meh"}\n```'
    score, pass_, _ = _parse_judge_output(raw)
    assert score == 0.5
    assert pass_ is False


def test_parse_judge_output_falls_back_to_brace_extract() -> None:
    raw = 'noise before {"score": 0.7, "pass": true, "reasoning": "ok"} noise after'
    score, pass_, _ = _parse_judge_output(raw)
    assert score == 0.7
    assert pass_ is True


def test_parse_judge_output_rejects_bad_score() -> None:
    with pytest.raises(JudgeError, match="out of"):
        _parse_judge_output('{"score": 1.5, "pass": true}')


def test_parse_judge_output_rejects_non_object() -> None:
    with pytest.raises(JudgeError, match="not a JSON object"):
        _parse_judge_output("[1, 2, 3]")


def test_parse_judge_output_infers_pass_from_score() -> None:
    _, pass_low, _ = _parse_judge_output('{"score": 0.4, "reasoning": "weak"}')
    assert pass_low is False
    _, pass_high, _ = _parse_judge_output('{"score": 0.6, "reasoning": "ok"}')
    assert pass_high is True


# ---------------------------------------------------------------------------
# judge_call — cache + live behavior
# ---------------------------------------------------------------------------

def test_judge_call_uses_cache(tmp_path: Path) -> None:
    prompt = "Q?"
    model = "claude-haiku-4-5"
    _make_cache_record(tmp_path, model, prompt, score=0.7, reasoning="cached hit")

    resp = judge_call(
        model=model, prompt=prompt, cache_dir=tmp_path, allow_live=False
    )
    assert resp.cached is True
    assert resp.score == 0.7
    assert resp.reasoning == "cached hit"


def test_judge_call_cache_miss_without_live(tmp_path: Path) -> None:
    with pytest.raises(JudgeError, match="cache miss"):
        judge_call(
            model="claude-haiku-4-5",
            prompt="unique-prompt-no-cache",
            cache_dir=tmp_path,
            allow_live=False,
        )


def test_judge_call_writes_cache_on_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live mode: stub call_live to return a fake API body, assert cache write."""
    prompt = "Q?"
    model = "claude-haiku-4-5"

    fake_response = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {"score": 0.6, "pass": True, "reasoning": "live test"}
                ),
            }
        ]
    }

    class _StubClient:
        def call_live(self, *, model: str, prompt: str, **_: Any) -> dict[str, Any]:
            return fake_response

    resp = judge_call(
        model=model,
        prompt=prompt,
        cache_dir=tmp_path,
        client=_StubClient(),
        allow_live=True,
    )
    assert resp.cached is False
    assert resp.score == 0.6
    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1
    record = json.loads(cache_files[0].read_text(encoding="utf-8"))
    assert record["model"] == model
    assert record["response"] == fake_response


def test_judge_client_live_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = JudgeClient(api_key=None)
    with pytest.raises(JudgeError, match="ANTHROPIC_API_KEY not set"):
        client.call_live(model="m", prompt="p")


def test_extract_assistant_text_handles_multi_block() -> None:
    text = _extract_assistant_text(
        {
            "content": [
                {"type": "text", "text": "alpha "},
                {"type": "image", "source": {}},
                {"type": "text", "text": "beta"},
            ]
        }
    )
    assert text == "alpha beta"


# ---------------------------------------------------------------------------
# Scorer end-to-end (cache-only)
# ---------------------------------------------------------------------------

def test_llm_judge_scorer_pass_with_cache(tmp_path: Path) -> None:
    traj = _write_trajectory(tmp_path, _events_for_l0_001())
    task = _task()

    cache_dir = tmp_path / "cache"
    summary = summarize_trajectory_for_judge(_events_for_l0_001())
    prompt = build_judge_prompt(task, summary)
    _make_cache_record(cache_dir, "claude-haiku-4-5", prompt, score=0.95)

    verdict = llm_judge_scorer(
        workdir=None,
        task=task,
        trajectory_path=traj,
        mode="replay",
        cache_dir=str(cache_dir),
        allow_live=False,
    )
    assert verdict.pass_ is True
    assert verdict.score == pytest.approx(0.95)
    assert verdict.detail["all_cached"] is True


def test_llm_judge_scorer_missing_cache_returns_error_verdict(tmp_path: Path) -> None:
    traj = _write_trajectory(tmp_path, _events_for_l0_001())
    verdict = llm_judge_scorer(
        workdir=None,
        task=_task(),
        trajectory_path=traj,
        mode="run",
        cache_dir=str(tmp_path / "empty"),
        allow_live=False,
    )
    assert verdict.pass_ is False
    assert verdict.score == 0.0
    assert "cache miss" in verdict.detail["error"]


def test_llm_judge_scorer_no_task_is_error(tmp_path: Path) -> None:
    traj = _write_trajectory(tmp_path, _events_for_l0_001())
    verdict = llm_judge_scorer(
        workdir=None,
        task=None,
        trajectory_path=traj,
        mode="run",
        cache_dir=str(tmp_path),
        allow_live=False,
    )
    assert verdict.pass_ is False
    assert "task required" in verdict.detail["error"]


def test_llm_judge_scorer_no_trajectory_is_error(tmp_path: Path) -> None:
    verdict = llm_judge_scorer(
        workdir=None,
        task=_task(),
        trajectory_path=None,
        mode="run",
        cache_dir=str(tmp_path),
        allow_live=False,
    )
    assert verdict.pass_ is False
    assert "no trajectory events" in verdict.detail["error"]


def test_llm_judge_ensemble_mean(tmp_path: Path) -> None:
    """n_judges=3, all cached at same score — mean returned, pass via majority."""
    traj = _write_trajectory(tmp_path, _events_for_l0_001())
    task = _task()
    cache_dir = tmp_path / "cache"
    summary = summarize_trajectory_for_judge(_events_for_l0_001())
    prompt = build_judge_prompt(task, summary)
    _make_cache_record(cache_dir, "claude-haiku-4-5", prompt, score=0.8)

    verdict = llm_judge_scorer(
        workdir=None,
        task=task,
        trajectory_path=traj,
        mode="run",
        cache_dir=str(cache_dir),
        allow_live=False,
        n_judges=3,
    )
    assert verdict.detail["n_judges"] == 3
    assert verdict.detail["scores"] == [0.8, 0.8, 0.8]
    assert verdict.score == pytest.approx(0.8)
    assert verdict.pass_ is True
