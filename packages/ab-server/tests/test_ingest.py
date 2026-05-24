from __future__ import annotations

import json
from pathlib import Path

import pytest
from ab_server.fetcher.ingest import _compute_passed, _config_from_trajectory, ingest_runs
from ab_server.fetcher.parser import iter_parsed_runs
from ab_server.leaderboard.queries import compute_leaderboard_response
from ab_server.models import PromptBlob, RegisteredRepo, Submission, TaskResult, User
from sqlmodel import Session, SQLModel, create_engine, select


def _write_run(run_dir: Path, run_id: str, task_id: str) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task_id}\nmodel: claude-sonnet\ntier: T0\nsuite: file-ops\ndataset_version: 0.0.1\nharness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    (run_dir / "scores.json").write_text(
        json.dumps({
            "run_id": run_id,
            "task_id": task_id,
            "total_score": 0.95,
            "pass": True,
            "per_pillar": {
                "correctness": 0.9,
                "context_efficiency": 0.8,
                "tool_skill": 0.7,
                "memory_specific": 0.6,
                "latency_cost": 0.5,
            },
        }) + "\n"
    )
    (run_dir / "trajectory.jsonl").write_text("{}\n")


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def repo(session: Session) -> RegisteredRepo:
    user = User(github_id="u1", handle="alice", avatar_url=None)
    session.add(user)
    session.commit()
    session.refresh(user)
    repo = RegisteredRepo(
        user_id=user.id,
        repo_url="https://github.com/alice/results",
        default_branch="main",
        is_public=True,
        status="registered",
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


def test_ingest_inserts_submissions_and_task_results(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run(clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001")
    _write_run(clone / "results" / "20260521T000100Z-run-2", "run-2", "L0_002")

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted, skipped = ingest_runs(session, repo, parsed)

    assert inserted == 2
    assert skipped == 0

    subs = session.exec(select(Submission)).all()
    assert len(subs) == 2
    trs = session.exec(select(TaskResult)).all()
    assert len(trs) == 2
    assert {tr.task_id for tr in trs} == {"L0_001", "L0_002"}
    assert all(tr.suite == "file-ops" for tr in trs)
    # Per-pillar scores must be propagated from scores.json["per_pillar"].
    # Regression guard: ingest used to only set score_total, leaving every
    # pillar column at the 0.0 default → leaderboard rendered all pillars
    # as 0.0% even for high-scoring submissions.
    for tr in trs:
        assert tr.score_correctness == 0.9
        assert tr.score_context_eff == 0.8
        assert tr.score_tool_skill == 0.7
        assert tr.score_memory == 0.6
        assert tr.score_latency == 0.5
        assert tr.score_total == 0.95


def _write_run_with_trajectory(
    run_dir: Path, run_id: str, task_id: str, traj_lines: list[dict]
) -> None:
    _write_run(run_dir, run_id, task_id)
    (run_dir / "trajectory.jsonl").write_text(
        "".join(json.dumps(ev) + "\n" for ev in traj_lines)
    )


def test_ingest_populates_tokens_and_turns_from_run_end_totals(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    traj = [
        {"event": "run_start", "run_id": "run-1", "task_id": "L0_001"},
        {"event": "turn", "idx": 0, "role": "user", "tokens_in": 100, "tokens_out": 0},
        {"event": "turn", "idx": 1, "role": "assistant", "tokens_in": 0, "tokens_out": 200},
        {"event": "turn", "idx": 2, "role": "assistant", "tokens_in": 0, "tokens_out": 150},
        {
            "event": "run_end",
            "status": "completed",
            "totals": {"tokens_in": 100, "tokens_out": 350},
        },
    ]
    _write_run_with_trajectory(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", traj
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted, _ = ingest_runs(session, repo, parsed)
    assert inserted == 1

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    # run_end totals are authoritative.
    assert tr.tokens_in == 100
    assert tr.tokens_out == 350
    assert tr.tokens_total == 450
    # turns_total counts assistant turns only.
    assert tr.turns_total == 2


def test_ingest_falls_back_to_per_turn_tokens_without_totals(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    traj = [
        {"event": "run_start", "run_id": "run-1", "task_id": "L0_001"},
        {"event": "turn", "idx": 0, "role": "user", "tokens_in": 40, "tokens_out": 0},
        {"event": "turn", "idx": 1, "role": "assistant", "tokens_in": 0, "tokens_out": 60},
        {"event": "run_end", "status": "completed"},
    ]
    _write_run_with_trajectory(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", traj
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.tokens_total == 100
    assert tr.turns_total == 1


def _write_run_partial_pillars(run_dir: Path, run_id: str, task_id: str) -> None:
    """A run whose scores.json carries only correctness + a genuine 0.0 latency;
    the other three pillar keys are ABSENT from per_pillar."""
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task_id}\nmodel: claude-sonnet\ntier: T0\nsuite: file-ops\ndataset_version: 0.0.1\nharness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    (run_dir / "scores.json").write_text(
        json.dumps({
            "run_id": run_id,
            "task_id": task_id,
            "total_score": 0.9,
            "pass": True,
            # context_efficiency / tool_skill / memory_specific keys ABSENT.
            "per_pillar": {"correctness": 0.9, "latency_cost": 0.0},
        }) + "\n"
    )
    (run_dir / "trajectory.jsonl").write_text("{}\n")


def test_ingest_writes_none_for_absent_pillar_and_keeps_genuine_zero(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run_partial_pillars(clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001")

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    # Measured pillars keep their value — including a genuine 0.0.
    assert tr.score_correctness == 0.9
    assert tr.score_latency == 0.0
    # Absent pillars become None (not measured), NOT a phantom 0.0.
    assert tr.score_context_eff is None
    assert tr.score_tool_skill is None
    assert tr.score_memory is None


def _write_run_with_verdicts(
    run_dir: Path,
    run_id: str,
    task_id: str,
    verdicts: list[dict],
    *,
    total_score: float | None = 0.5,
    per_pillar: dict | None = None,
) -> None:
    """Write a run dir whose scores.json["verdicts"] is the supplied list.

    Pass ``total_score=None`` and ``per_pillar=None`` to exercise the strict-AND
    fallback path (no aggregate available — back-compat behaviour).
    """
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task_id}\nmodel: claude-sonnet\ntier: T0\nsuite: file-ops\ndataset_version: 0.0.1\nharness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    scores: dict = {
        "run_id": run_id,
        "task_id": task_id,
        "pass": all(v.get("pass", False) for v in verdicts) if verdicts else False,
        "verdicts": verdicts,
    }
    if total_score is not None:
        scores["total_score"] = total_score
    if per_pillar is not None:
        scores["per_pillar"] = per_pillar
    (run_dir / "scores.json").write_text(json.dumps(scores) + "\n")
    (run_dir / "trajectory.jsonl").write_text("{}\n")


def test_ingest_passed_all_pass(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """passed=True when every decided scorer passes."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    verdicts = [
        {"scorer_name": "schema", "kind": "schema", "pass": True, "score": 1.0, "detail": {}},
        {"scorer_name": "file_diff", "kind": "deterministic", "pass": True, "score": 1.0, "detail": {}},
    ]
    _write_run_with_verdicts(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", verdicts
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.passed is True


def test_ingest_passed_one_fail(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """passed=False when at least one decided scorer fails and no aggregate is present.

    Without total_score or per_pillar the helper falls back to strict-AND, so
    a single failing verdict makes the whole task fail.
    """
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    verdicts = [
        {"scorer_name": "schema", "kind": "schema", "pass": True, "score": 1.0, "detail": {}},
        {"scorer_name": "file_diff", "kind": "deterministic", "pass": False, "score": 0.0, "detail": {}},
    ]
    _write_run_with_verdicts(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", verdicts,
        total_score=None, per_pillar=None,
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.passed is False


def test_ingest_passed_no_decided_verdicts(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """passed=None when verdicts list is empty and no aggregate is present."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run_with_verdicts(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", [],
        total_score=None, per_pillar=None,
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.passed is None


def test_ingest_idempotent_second_call(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run(clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001")
    _write_run(clone / "results" / "20260521T000100Z-run-2", "run-2", "L0_002")

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted1, skipped1 = ingest_runs(session, repo, parsed)
    inserted2, skipped2 = ingest_runs(session, repo, parsed)

    assert (inserted1, skipped1) == (2, 0)
    assert (inserted2, skipped2) == (0, 2)
    subs = session.exec(select(Submission)).all()
    assert len(subs) == 2


# ── _config_from_trajectory unit tests ──────────────────────────────────────


def test_config_from_trajectory_present(tmp_path: Path) -> None:
    """run_start with harness and reasoning.effort → all four fields extracted."""
    traj = tmp_path / "trajectory.jsonl"
    traj.write_text(
        json.dumps({
            "event": "run_start",
            "harness": "claude-code",
            "reasoning": {"effort": "high", "budget_tokens": 1000},
            "prompt_label": "my-prompt",
            "system_prompt_verbatim": "You are a helpful assistant.",
        }) + "\n"
        + json.dumps({"event": "run_end"}) + "\n"
    )
    harness, effort, prompt_label, system_prompt_verbatim = _config_from_trajectory(traj)
    assert harness == "claude-code"
    assert effort == "high"
    assert prompt_label == "my-prompt"
    assert system_prompt_verbatim == "You are a helpful assistant."


def test_config_from_trajectory_reasoning_null(tmp_path: Path) -> None:
    """run_start with reasoning=null → harness extracted, effort is None."""
    traj = tmp_path / "trajectory.jsonl"
    traj.write_text(
        json.dumps({"event": "run_start", "harness": "mock", "reasoning": None}) + "\n"
    )
    harness, effort, prompt_label, system_prompt_verbatim = _config_from_trajectory(traj)
    assert harness == "mock"
    assert effort is None
    assert prompt_label is None
    assert system_prompt_verbatim is None


def test_config_from_trajectory_no_run_start(tmp_path: Path) -> None:
    """Trajectory without run_start → (None, None, None, None)."""
    traj = tmp_path / "trajectory.jsonl"
    traj.write_text(json.dumps({"event": "turn", "idx": 0}) + "\n")
    assert _config_from_trajectory(traj) == (None, None, None, None)


def test_config_from_trajectory_missing_file(tmp_path: Path) -> None:
    """Non-existent trajectory path → (None, None, None, None)."""
    assert _config_from_trajectory(tmp_path / "no_such.jsonl") == (None, None, None, None)


def test_ingest_persists_harness_and_effort(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """harness + effort are read from run_start and persisted on TaskResult."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    run_dir = clone / "results" / "20260521T000000Z-run-1"
    traj = [
        {"event": "run_start", "run_id": "run-1", "task_id": "L0_001",
         "harness": "claude-code", "reasoning": {"effort": "medium"}},
        {"event": "run_end", "status": "completed"},
    ]
    _write_run_with_trajectory(run_dir, "run-1", "L0_001", traj)

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted, _ = ingest_runs(session, repo, parsed)
    assert inserted == 1

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.harness == "claude-code"
    assert tr.effort == "medium"


# ── _compute_passed strict-AND semantics (B2 reverted) ──────────────────────

def test_compute_passed_total_score_does_not_override_failing_verdict() -> None:
    """B2 revert: total_score=0.98 with one failing verdict → passed=False.

    Earlier B2 made total_score>=0.5 override the chain rule, but that inflated
    pass-rates to ~100% (partial runs marked pass even when an objective scorer
    failed). After revert the chain rule is the source of truth: any decided
    pass=False verdict makes the task fail, regardless of total_score.
    """
    verdicts = [
        {"scorer_name": "correctness", "pass": True, "score": 1.0},
        {"scorer_name": "latency_cost", "pass": False, "score": 0.1},
    ]
    result = _compute_passed(verdicts, total_score=0.98)
    assert result is False, (
        f"expected False (strict-AND: one failing verdict → fail) but got {result!r}"
    )


def test_compute_passed_total_score_low_does_not_override_passing_chain() -> None:
    """B2 revert: total_score=0.3 with all verdicts passing → passed=True.

    The strict-AND chain wins over any total_score signal. If every decided
    scorer returns pass=True, the task is passed even when the weighted
    aggregate score happens to be low — total_score is informational only.
    """
    verdicts = [
        {"scorer_name": "correctness", "pass": True, "score": 0.3},
        {"scorer_name": "context_efficiency", "pass": True, "score": 0.3},
    ]
    result = _compute_passed(verdicts, total_score=0.3)
    assert result is True, (
        f"expected True (strict-AND: all decided pass) but got {result!r}"
    )


def test_compute_passed_no_aggregate_falls_back_to_strict_and() -> None:
    """Case 3: no aggregate, all decided verdicts pass → True (back-compat).

    When neither total_score nor per_pillar are supplied (old scores.json), the
    helper falls back to the original strict-AND logic.
    """
    verdicts = [
        {"scorer_name": "schema", "pass": True, "score": 1.0},
        {"scorer_name": "file_diff", "pass": True, "score": 1.0},
    ]
    result = _compute_passed(verdicts)
    assert result is True, (
        f"expected True (strict-AND fallback, all verdicts pass) but got {result!r}"
    )


def test_compute_passed_zero_verdicts_no_aggregate_returns_none() -> None:
    """Case 4: zero verdicts and no aggregate → None ("not measured")."""
    result = _compute_passed([], total_score=None, per_pillar=None)
    assert result is None, (
        f"expected None (no data to decide on) but got {result!r}"
    )


def test_two_configs_produce_two_leaderboard_rows(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """Same (model, operator, tier) but different harness → two distinct rows."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)

    traj_a = [
        {"event": "run_start", "run_id": "run-a", "task_id": "L0_001",
         "harness": "claude-code", "reasoning": {"effort": "low"}},
        {"event": "run_end", "status": "completed"},
    ]
    traj_b = [
        {"event": "run_start", "run_id": "run-b", "task_id": "L0_002",
         "harness": "codex-cli", "reasoning": {"effort": "low"}},
        {"event": "run_end", "status": "completed"},
    ]
    _write_run_with_trajectory(clone / "results" / "20260521T000000Z-run-a", "run-a", "L0_001", traj_a)
    _write_run_with_trajectory(clone / "results" / "20260521T000100Z-run-b", "run-b", "L0_002", traj_b)

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted, _ = ingest_runs(session, repo, parsed)
    assert inserted == 2

    resp = compute_leaderboard_response(session)
    # Both runs share model=claude-sonnet, operator=alice (from repo fixture),
    # tier=T0 — but differ in harness → must produce two rows.
    assert len(resp.rows) == 2
    harnesses = {r.harness for r in resp.rows}
    assert harnesses == {"claude-code", "codex-cli"}


# ── prompt_label + prompt_blobs tests ────────────────────────────────────────


# Sandbox preamble injected by base.compose_system_prompt for all runs.
_SANDBOX_PREAMBLE = "You are a helpful assistant. Complete the task precisely."
# Operator CLAUDE.md text used in custom-prompt tests.
_OPERATOR_CLAUDE_MD = "You are a strict code reviewer.\nFocus on correctness."
# Full composed system_prompt_verbatim as emitted by base.compose_system_prompt
# when --claude-md is active: preamble + marker + operator CLAUDE.md.
_CUSTOM_SYSTEM_PROMPT = (
    _SANDBOX_PREAMBLE
    + "\n\n--- project CLAUDE.md ---\n"
    + _OPERATOR_CLAUDE_MD
)


def _write_run_with_custom_prompt(
    run_dir: Path,
    run_id: str,
    task_id: str,
    tier_hash: str,
    prompt_label: str,
    system_prompt_verbatim: str,
) -> None:
    """Write a run dir whose trajectory has a custom prompt on run_start.

    system_prompt_verbatim should be the full composed string (preamble +
    marker + operator text) as emitted by base.compose_system_prompt.
    """
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task_id}\nmodel: claude-sonnet\ntier: T2\n"
        f"tier_hash: {tier_hash}\nsuite: file-ops\ndataset_version: 0.0.1\n"
        "harness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    (run_dir / "scores.json").write_text(
        json.dumps({
            "run_id": run_id,
            "task_id": task_id,
            "model": "claude-sonnet",
            "tier": "T2",
            "tier_hash": tier_hash,
            "dataset_version": "0.0.1",
            "total_score": 0.8,
            "pass": True,
            "per_pillar": {"correctness": 0.8},
        }) + "\n"
    )
    traj = [
        {
            "event": "run_start",
            "run_id": run_id,
            "task_id": task_id,
            "harness": "claude-code",
            "tier_hash": tier_hash,
            "prompt_label": prompt_label,
            "system_prompt_verbatim": system_prompt_verbatim,
        },
        {"event": "run_end", "status": "completed"},
    ]
    (run_dir / "trajectory.jsonl").write_text(
        "".join(json.dumps(ev) + "\n" for ev in traj)
    )


def test_ingest_persists_prompt_label_on_task_result(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """prompt_label from run_start is persisted on TaskResult.prompt_label."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run_with_custom_prompt(
        clone / "results" / "20260521T000000Z-run-1",
        "run-1",
        "L0_001",
        tier_hash="abc123",
        prompt_label="strict-reviewer",
        system_prompt_verbatim=_CUSTOM_SYSTEM_PROMPT,
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted, _ = ingest_runs(session, repo, parsed)
    assert inserted == 1

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.prompt_label == "strict-reviewer"


def test_ingest_upserts_prompt_blob(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """Ingesting a custom-prompt run creates a PromptBlob keyed by tier_hash.

    blob.text must be the CLEAN operator CLAUDE.md — no sandbox preamble,
    no marker line.
    """
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run_with_custom_prompt(
        clone / "results" / "20260521T000000Z-run-1",
        "run-1",
        "L0_001",
        tier_hash="deadbeef",
        prompt_label="my-prompt",
        system_prompt_verbatim=_CUSTOM_SYSTEM_PROMPT,
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    blob = session.get(PromptBlob, "deadbeef")
    assert blob is not None
    # Stored text must be the clean operator CLAUDE.md, not the full composite.
    assert blob.text == _OPERATOR_CLAUDE_MD
    assert _SANDBOX_PREAMBLE not in blob.text
    assert "--- project CLAUDE.md ---" not in blob.text
    assert blob.label == "my-prompt"


def test_ingest_prompt_blob_dedup(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """Ingesting the same prompt hash twice keeps only one PromptBlob row."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    # Two runs with the same tier_hash (same custom prompt) but different run_ids.
    _write_run_with_custom_prompt(
        clone / "results" / "20260521T000000Z-run-1",
        "run-1",
        "L0_001",
        tier_hash="sharedprompt",
        prompt_label="shared",
        system_prompt_verbatim=_CUSTOM_SYSTEM_PROMPT,
    )
    _write_run_with_custom_prompt(
        clone / "results" / "20260521T000100Z-run-2",
        "run-2",
        "L0_002",
        tier_hash="sharedprompt",
        prompt_label="shared",
        system_prompt_verbatim=_CUSTOM_SYSTEM_PROMPT,
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted, _ = ingest_runs(session, repo, parsed)
    assert inserted == 2

    blobs = session.exec(select(PromptBlob)).all()
    assert len(blobs) == 1
    assert blobs[0].prompt_hash == "sharedprompt"


def test_ingest_no_prompt_blob_without_verbatim(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """A run without system_prompt_verbatim creates no PromptBlob row."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run(clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001")

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    blobs = session.exec(select(PromptBlob)).all()
    assert blobs == []


def test_ingest_no_prompt_blob_for_vanilla_run(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """A run with system_prompt_verbatim but NO custom marker creates no blob.

    Vanilla runs emit only the sandbox guardrail in system_prompt_verbatim
    (no '--- project CLAUDE.md ---' marker). They must NOT produce a
    prompt_blobs row — the vanilla guardrail is not an operator custom prompt.
    """
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    run_dir = clone / "results" / "20260521T000000Z-run-1"
    _write_run_with_custom_prompt(
        run_dir,
        "run-1",
        "L0_001",
        tier_hash="vanillahash",
        prompt_label="",
        # No marker — vanilla run, only the sandbox preamble.
        system_prompt_verbatim=_SANDBOX_PREAMBLE,
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    blobs = session.exec(select(PromptBlob)).all()
    assert blobs == [], "vanilla run must not produce a prompt_blob"
