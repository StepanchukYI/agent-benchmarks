"""Replay: returns advisory verdict when ab_harness not installed; real verdicts otherwise."""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime

from ab_datasets.schemas import ScorerVerdict, Tier, Totals, Trajectory
from ab_sdk import replay, write_run_dir


def _trajectory() -> Trajectory:
    now = datetime.now(UTC)
    return Trajectory(
        run_id="run-rp",
        task_id="L0_001",
        model="claude",
        harness="claude-code-cli@0.4.1",
        tier=Tier.T0,
        dataset_version="ab-datasets==0.0.1",
        started_at=now,
        finished_at=now,
        turns=[],
        status="completed",
        totals=Totals(tokens_in=0, tokens_out=0, latency_ms=0, cost_usd=0.0, score=0.0),
    )


def _write_run(tmp_path):
    write_run_dir(
        tmp_path,
        _trajectory(),
        {"model": "claude", "tier": "T0", "dataset_version": "0.0.1"},
    )


def test_replay_returns_verdicts_or_advisory(tmp_path):
    _write_run(tmp_path)

    try:
        importlib.import_module("ab_harness.scorers.runner")
        has_runner = True
    except ImportError:
        has_runner = False

    if has_runner:
        from ab_datasets.schemas import (
            Difficulty,
            Layer,
            ScorerKind,
            ScorerSpec,
            Task,
            TaskConfig,
            TrustTier,
            Visibility,
        )

        task = Task(
            id="replay-test",
            layer=Layer.L0,
            suite="replay",
            title="replay",
            description="",
            scorer_chain=[
                ScorerSpec(name="privacy_check", kind=ScorerKind.privacy_check, config={})
            ],
            config=TaskConfig(required_tier="T0", recommended_tier="T0"),
            difficulty=Difficulty.easy,
            visibility=Visibility.public,
            trust_tier_ceiling=TrustTier.verified,
        )
        verdicts = replay(tmp_path, scorer_chain=task)
        assert isinstance(verdicts, list)
        assert all(isinstance(v, ScorerVerdict) for v in verdicts)
        assert len(verdicts) == 1
        assert verdicts[0].scorer_name == "privacy_check"
    else:
        verdicts = replay(tmp_path)
        assert isinstance(verdicts, list)
        assert len(verdicts) == 1
        assert verdicts[0].scorer_name == "replay_advisory"
        assert verdicts[0].pass_ is False
        detail = verdicts[0].detail
        assert isinstance(detail, dict) and detail.get("advisory") is True


def test_replay_advisory_when_harness_runner_unavailable(tmp_path, monkeypatch):
    _write_run(tmp_path)

    monkeypatch.setitem(sys.modules, "ab_harness.scorers.runner", None)

    verdicts = replay(tmp_path)
    assert len(verdicts) == 1
    assert verdicts[0].scorer_name == "replay_advisory"
    assert verdicts[0].pass_ is False
