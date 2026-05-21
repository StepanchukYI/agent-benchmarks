from __future__ import annotations

from datetime import UTC, datetime

from ab_datasets.schemas import (
    Difficulty,
    Fixture,
    Layer,
    RunStatus,
    ScorerKind,
    ScorerSpec,
    ScorerVerdict,
    Submission,
    Task,
    TaskConfig,
    Tier,
    TierManifest,
    Totals,
    Trajectory,
    TrustTier,
    Turn,
    Visibility,
)


def _task_config() -> TaskConfig:
    return TaskConfig(required_tier="T0", recommended_tier="T0")


def test_task_minimal() -> None:
    task = Task(
        id="L0_001",
        layer=Layer.L0,
        suite="file-ops",
        title="Create a file",
        description="Create an empty file at the given path.",
        config=_task_config(),
    )
    assert task.layer is Layer.L0
    assert task.visibility is Visibility.public
    assert task.trust_tier_ceiling is TrustTier.verified
    assert task.difficulty is Difficulty.medium
    assert isinstance(task.model_json_schema(), dict)


def test_fixture_minimal() -> None:
    fx = Fixture(
        id="repo_small_v1",
        kind="repo",
        sha256="0" * 64,
        path="fixtures/repos/small_v1.tar.gz",
        size=1024,
    )
    assert fx.visibility is Visibility.public
    assert "properties" in fx.model_json_schema()


def test_scorer_spec_and_verdict() -> None:
    spec = ScorerSpec(name="schema_validator", kind=ScorerKind.deterministic, config={"required_fields": ["x"]})
    verdict = ScorerVerdict.model_validate(
        {"scorer_name": "schema_validator", "kind": "deterministic", "pass": True, "score": 1.0, "detail": "ok"}
    )
    assert spec.kind is ScorerKind.deterministic
    assert verdict.pass_ is True
    dumped = verdict.model_dump(by_alias=True)
    assert dumped["pass"] is True


def test_tier_manifest_minimal() -> None:
    manifest = TierManifest(tier=Tier.T2, description="Personal tier")
    assert manifest.tier is Tier.T2
    assert manifest.skills == []
    assert "properties" in manifest.model_json_schema()


def test_trajectory_minimal() -> None:
    started = datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC)
    traj = Trajectory(
        run_id="run-1",
        task_id="L0_001",
        model="claude-sonnet-4-5",
        harness="claude-code-cli@0.4.1",
        tier=Tier.T0,
        dataset_version="ab-datasets==0.0.1",
        started_at=started,
        turns=[Turn(idx=0, role="user", model_output="")],
        totals=Totals(score=1.0),
        status=RunStatus.completed,
    )
    assert traj.turns[0].role == "user"
    assert traj.totals is not None
    assert traj.status is RunStatus.completed
    assert "properties" in traj.model_json_schema()


def test_submission_minimal() -> None:
    sub = Submission(
        id="sub-1",
        source_repo="https://github.com/x/y",
        source_commit_sha="abc",
        registered_repo_id="rr-1",
        trajectory_path="results/run-1/trajectory.jsonl",
        trust_tier=TrustTier.self_reported,
        submitted_at=datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC),
        model="claude-sonnet-4-5",
        tier=Tier.T0,
        dataset_version="ab-datasets==0.0.1",
    )
    assert sub.trust_tier is TrustTier.self_reported
    assert "properties" in sub.model_json_schema()
