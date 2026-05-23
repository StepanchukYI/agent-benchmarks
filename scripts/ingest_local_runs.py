#!/usr/bin/env python3
"""Ingest local `ab run` results into the server DB as Submissions.

For a homelab deploy where the leaderboard should show REAL bench
results from the operator's own runs (not fake seed data), this script
walks a results directory tree and inserts one Submission + TaskResult
row per run.

Usage:

    python scripts/ingest_local_runs.py \\
        --results-root /tmp/ab-matrix \\
        --repo-handle stepanchukyi \\
        --repo-url https://github.com/StepanchukYI/agent-benchmarks-runs \\
        --visibility public

What gets ingested:

* One `User` row per --repo-handle if missing.
* One `RegisteredRepo` row if missing (idempotent on repo_url).
* For every `<results-root>/<utc>-run-*/scores.json`:
  - One `Submission` row.
  - One `TaskResult` row with the per-pillar scores from scores.json.
  - trajectory_blob_ref points to the on-disk trajectory.jsonl.

Idempotent: re-running skips any (registered_repo_id, source_commit_sha,
source_path) combo already present.

Privacy gate enforced before insert — `ab publish` rules apply. A run
with high-severity privacy hits is REFUSED; scrub first via
`scripts/privacy_scrub.py`.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "packages" / "ab-server"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "ab-sdk"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "ab-datasets"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "ab-harness"))

from ab_sdk.publish_gate import check_publish_ready  # noqa: E402
from ab_server.config import Settings  # noqa: E402
from ab_server.db import get_engine  # noqa: E402
from ab_server.fetcher.ingest import (  # noqa: E402
    _compute_passed,
    _config_from_trajectory,
    _extract_custom_prompt,
    _pillar_score,
    _suite_from_task,
    _token_turn_counts,
    _upsert_prompt_blob,
)
from ab_server.models import (  # noqa: E402
    RegisteredRepo,
    Submission,
    TaskResult,
    User,
)
from sqlmodel import Session, select  # noqa: E402

_log = logging.getLogger("ingest")


def _ensure_user(session: Session, *, handle: str, github_id: str) -> User:
    user = session.exec(select(User).where(User.handle == handle)).first()
    if user is not None:
        return user
    user = User(handle=handle, github_id=github_id, avatar_url=None)
    session.add(user)
    session.commit()
    session.refresh(user)
    _log.info("created user %s (id=%s)", handle, user.id)
    return user


def _ensure_repo(
    session: Session,
    *,
    user: User,
    repo_url: str,
    is_public: bool,
) -> RegisteredRepo:
    repo = session.exec(
        select(RegisteredRepo).where(RegisteredRepo.repo_url == repo_url)
    ).first()
    if repo is not None:
        if repo.is_public != is_public:
            repo.is_public = is_public
            session.add(repo)
            session.commit()
            session.refresh(repo)
        return repo
    repo = RegisteredRepo(
        user_id=user.id,
        repo_url=repo_url,
        default_branch="main",
        is_public=is_public,
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    _log.info("created repo %s (id=%s)", repo_url, repo.id)
    return repo


def _gather_run_dirs(results_root: Path) -> list[Path]:
    out: list[Path] = []
    for d in sorted(results_root.iterdir()):
        if not d.is_dir():
            continue
        if not (d / "scores.json").exists():
            continue
        if not (d / "trajectory.jsonl").exists():
            continue
        out.append(d)
    return out


def _load_scores(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _existing_submission(
    session: Session,
    repo_id: UUID,
    commit_sha: str,
    source_path: str,
) -> Submission | None:
    return session.exec(
        select(Submission)
        .where(Submission.registered_repo_id == repo_id)
        .where(Submission.source_commit_sha == commit_sha)
        .where(Submission.source_path == source_path)
    ).first()


def _pillar_scores(scores: dict[str, Any]) -> dict[str, float | None]:
    # None when the pillar key is absent — "not measured", not 0.0.
    # Uses the shared _pillar_score helper from fetcher/ingest to stay in sync.
    pp = scores.get("per_pillar") or {}
    return {
        "score_correctness": _pillar_score(pp, "correctness"),
        "score_context_eff": _pillar_score(pp, "context_efficiency"),
        "score_tool_skill": _pillar_score(pp, "tool_skill"),
        "score_memory": _pillar_score(pp, "memory_specific"),
        "score_latency": _pillar_score(pp, "latency_cost"),
        "score_total": float(scores.get("total_score") or 0.0),
    }


def _ingest_one(
    session: Session,
    *,
    run_dir: Path,
    repo: RegisteredRepo,
    require_privacy_pass: bool,
) -> tuple[Submission | None, str]:
    if require_privacy_pass:
        ok, issues = check_publish_ready(run_dir)
        if not ok:
            return None, "privacy gate failed: " + "; ".join(issues[:3])

    scores = _load_scores(run_dir / "scores.json")
    task_id = str(scores["task_id"])
    model = str(scores["model"])
    tier = str(scores["tier"])
    dataset_version = str(scores.get("dataset_version", "ab-datasets==0.0.1"))
    run_id = str(scores["run_id"])

    commit_sha = f"local:{run_dir.name}"
    source_path = run_dir.name

    if _existing_submission(session, repo.id, commit_sha, source_path):
        return None, "skipped (already ingested)"

    submission = Submission(
        registered_repo_id=repo.id,
        source_commit_sha=commit_sha,
        source_path=source_path,
        trust_tier="self_reported",
        ingested_at=datetime.now(UTC),
        model=model,
        tier=tier,
        dataset_version=dataset_version,
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)

    # Suite: prefer scores.json "suite" key (set by runner), fall back to
    # _suite_from_task — same logic as the fetcher (no metadata.yaml here).
    suite = str(scores.get("suite") or _suite_from_task(task_id))
    tier_hash = scores.get("tier_hash") or ""

    passed = _compute_passed(scores.get("verdicts") or [])
    # status mirrors fetcher: "passed"/"failed" based on verdicts.
    # datasets.py pass_rate_30d reads the authoritative `passed` flag (B8), not
    # status — so this is purely informational / run-lifecycle context.
    status_value = "passed" if passed else "failed"

    # Cost + latency: trajectory run_end totals (primary), then scores.json
    # fallback keys — mirrors the fetcher's source priority (minus metadata.yaml
    # which local runs don't have).
    cost_usd = 0.0
    latency_ms = 0
    try:
        with (run_dir / "trajectory.jsonl").open("r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev.get("event") == "run_end":
                    totals = ev.get("totals") or {}
                    cost_usd = float(totals.get("cost_usd") or 0.0)
                    latency_ms = int(totals.get("latency_ms") or 0)
    except OSError:
        pass
    # scores.json fallback (matches fetcher's scores.get("cost_usd") chain)
    if not cost_usd:
        cost_usd = float(
            scores.get("cost_usd") or scores.get("total_cost_usd") or 0.0
        )
    if not latency_ms:
        latency_ms = int(
            scores.get("latency_ms") or scores.get("total_latency_ms") or 0
        )
    # NOTE: _token_turn_counts opens the trajectory a second time; the block
    # above already opened it for cost/latency. Minor double-read in a one-off
    # script — acceptable per task scope; not worth merging without a broader
    # cost/latency refactor.
    tokens_total, tokens_in, tokens_out, turns_total = _token_turn_counts(
        run_dir / "trajectory.jsonl"
    )
    harness, effort, prompt_label, system_prompt_verbatim = _config_from_trajectory(
        run_dir / "trajectory.jsonl"
    )

    # Upsert prompt blob only when a custom CLAUDE.md was active.
    # _extract_custom_prompt returns None for vanilla runs (no marker) so
    # the sandbox-guardrail-only text never lands in prompt_blobs.
    custom_text = _extract_custom_prompt(system_prompt_verbatim)
    if custom_text and tier_hash:
        _upsert_prompt_blob(
            session,
            prompt_hash=tier_hash,
            text=custom_text,
            label=prompt_label,
        )

    result = TaskResult(
        run_id=None,
        submission_id=submission.id,
        task_id=task_id,
        suite=suite,
        model=model,
        tier=tier,
        tier_hash=tier_hash,
        status=status_value,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        tokens_total=tokens_total,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        turns_total=turns_total,
        trajectory_blob_ref=str((run_dir / "trajectory.jsonl").resolve()),
        passed=passed,
        harness=harness,
        effort=effort,
        prompt_label=prompt_label,
        **_pillar_scores(scores),
    )
    session.add(result)
    session.commit()
    return submission, f"ingested run_id={run_id}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--repo-handle", type=str, required=True)
    parser.add_argument("--repo-url", type=str, required=True)
    parser.add_argument("--repo-github-id", type=str, default=None)
    parser.add_argument(
        "--visibility", choices=["public", "private"], default="public"
    )
    parser.add_argument(
        "--no-privacy-gate", action="store_true",
        help="Skip the high-severity privacy scan (dev only).",
    )
    parser.add_argument("--database-url", type=str, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.results_root.exists() or not args.results_root.is_dir():
        print(f"results-root not found: {args.results_root}", file=sys.stderr)
        return 2

    if args.database_url:
        import os

        os.environ["DATABASE_URL"] = args.database_url
        _ = Settings()

    run_dirs = _gather_run_dirs(args.results_root)
    if not run_dirs:
        print(
            f"no run dirs (scores.json + trajectory.jsonl) under {args.results_root}",
            file=sys.stderr,
        )
        return 1

    _log.info("found %d run dirs under %s", len(run_dirs), args.results_root)

    engine = get_engine()
    inserted = 0
    skipped = 0
    refused = 0
    with Session(engine) as session:
        user = _ensure_user(
            session,
            handle=args.repo_handle,
            github_id=args.repo_github_id or args.repo_handle,
        )
        repo = _ensure_repo(
            session,
            user=user,
            repo_url=args.repo_url,
            is_public=(args.visibility == "public"),
        )
        for run_dir in run_dirs:
            _, msg = _ingest_one(
                session,
                run_dir=run_dir,
                repo=repo,
                require_privacy_pass=not args.no_privacy_gate,
            )
            _log.info("  %s :: %s", run_dir.name, msg)
            if "ingested" in msg:
                inserted += 1
            elif "skipped" in msg:
                skipped += 1
            else:
                refused += 1

    print(
        f"\nsummary: inserted={inserted} skipped={skipped} refused={refused}"
    )
    return 0 if refused == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
