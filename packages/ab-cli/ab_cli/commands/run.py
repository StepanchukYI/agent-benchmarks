"""`ab run` — execute a benchmark suite against a model, write a results dir."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from ab_datasets.schemas import ScorerVerdict, Task, Tier
from ab_harness.runners import (
    ClaudeCodeRunner,
    CodexCLIRunner,
    GeminiCLIRunner,
    MockRunner,
    make_runner,
)
from ab_harness.sandbox import materialize
from ab_harness.scorers.runner import run_scorer_chain
from ab_harness.trajectory.splice import splice_scorer_events
from ab_harness.trajectory.writer import TrajectoryWriter
from ab_sdk.manifest import write_metadata
from ab_sdk.results import SCORES_FILE, ScoresFile, build_scores_payload

from .._discover import (
    discover_tasks,
    seed_workdir_from_fixture,
)
from .._discover import (
    tier_root as _tier_root_default,
)
from ..ui import console


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _make_runner(
    runner_name: str,
    model: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    system_prompt: str | None = None,
    effort: str | None = None,
    env_overrides: dict[str, str] | None = None,
) -> Any:
    """Map a CLI `--runner` string + `--model` to a BaseRunner.

    Native fast paths first (claude-code / codex-cli / gemini-cli + mock);
    everything else delegates to ``ab_harness.runners.make_runner`` which
    handles the full scaffold/model matrix (anthropic-compat,
    openai-compat, local, + stubs for opencode/pi-agent/hermes-agent/
    nanobot/cursor).
    """
    if runner_name == "mock":
        return MockRunner(model=model)
    if runner_name in {"claude-code", "claude-code-cli", "claude"}:
        return ClaudeCodeRunner(
            model=model, effort=effort, env_overrides=env_overrides
        )
    if runner_name in {"codex-cli", "codex"}:
        return CodexCLIRunner(model=model, reasoning_effort=effort)
    if runner_name in {"gemini-cli", "gemini"}:
        return GeminiCLIRunner(model=model, reasoning_effort=effort)
    return make_runner(
        runner=runner_name,
        model=model,
        api_key=api_key,
        base_url=base_url,
        system_prompt=system_prompt,
    )


def _scores_payload(
    *,
    run_id: str,
    task_id: str,
    model: str,
    tier: str,
    dataset_version: str,
    verdicts: list[ScorerVerdict],
    task: Task | None = None,
) -> dict[str, Any]:
    payload = build_scores_payload(
        run_id=run_id,
        task_id=task_id,
        model=model,
        tier=tier,
        dataset_version=dataset_version,
        verdicts=verdicts,
        task=task,
    )
    return payload


def run(
    suite: str = typer.Option(..., help="Suite id, e.g. L0_smoke, or a single task id."),
    model: str = typer.Option("claude-sonnet-4-5", help="Model id."),
    tier: str = typer.Option("T0", help="Initial config tier (T0/T1/T2/T3)."),
    task: str | None = typer.Option(None, help="Single task id override."),
    runner: str = typer.Option(
        "claude-code",
        help=(
            "Runner: 'claude-code' (default) | 'mock' | 'anthropic-compat' | "
            "'openai-compat' | 'local' | 'codex-cli' | 'gemini-cli' | "
            "'opencode' | 'pi-agent' | 'hermes-agent' | 'nanobot' | 'cursor'."
        ),
    ),
    api_key: str | None = typer.Option(
        None,
        help=(
            "API key override for HTTP-driven runners. Defaults to the "
            "appropriate env var (ANTHROPIC_API_KEY / OPENAI_API_KEY). "
            "Empty allowed for local runners."
        ),
    ),
    base_url: str | None = typer.Option(
        None,
        help=(
            "Override the runner's base URL (Anthropic-compat / OpenAI-compat / "
            "local scaffolds). Defaults from the model registry / scaffold port."
        ),
    ),
    system_prompt: str | None = typer.Option(
        None,
        help="System prompt passed to HTTP-driven runners.",
    ),
    effort: str | None = typer.Option(
        None,
        help=(
            "Reasoning effort for claude-code: low|medium|high|xhigh|max. "
            "Maps to claude CLI's --effort. Other runners may use it via "
            "their own reasoning controls in a future commit."
        ),
    ),
    env: list[str] | None = typer.Option(
        None,
        "--env",
        help=(
            "KEY=VALUE env override passed to the runner's subprocess. "
            "Repeatable. Used to point claude-code CLI at vendor-routed "
            "Anthropic-compat endpoints (Zhipu, MiniMax, Kimi, DeepSeek): "
            "--env ANTHROPIC_BASE_URL=https://api.z.ai/api/anthropic "
            "--env ANTHROPIC_AUTH_TOKEN=$GLM_KEY "
            "--env ANTHROPIC_MODEL=GLM-5.1"
        ),
    ),
    vendor: str | None = typer.Option(
        None,
        help=(
            "Shortcut to set ANTHROPIC_BASE_URL from the model registry. "
            "Values: anthropic | zhipu | minimax | moonshot | deepseek. "
            "Auth token must be passed separately via --env "
            "ANTHROPIC_AUTH_TOKEN=$VENDOR_KEY."
        ),
    ),
    results_root: Path = typer.Option(
        Path.home() / ".ab" / "results",
        help=(
            "Root directory under which run dirs are created. "
            "Defaults to ~/.ab/results so workdirs live outside the repo "
            "and runners don't auto-discover parent CLAUDE.md / skills."
        ),
    ),
    dataset_version: str = typer.Option(
        "ab-datasets==0.0.1", help="Recorded in trajectory.run_start."
    ),
) -> None:
    """Run a suite (or single task) against a model at a tier; emit results/<utc>-<id>/."""
    try:
        tier_enum = Tier(tier)
    except ValueError as exc:
        console.print(f"[red]unknown tier {tier!r}[/red]")
        raise typer.Exit(2) from exc

    try:
        tasks = discover_tasks(suite, single_task=task)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc

    results_root = Path(results_root)
    results_root.mkdir(parents=True, exist_ok=True)
    console.print(f"results_root={results_root}")

    overall_ok = True
    for t in tasks:
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        run_dir = results_root / f"{_utc_stamp()}-{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        workdir = run_dir / "workdir"
        workdir.mkdir(parents=True, exist_ok=True)

        started_at = datetime.now(UTC).isoformat()
        materialized = materialize(_tier_root_default(), tier_enum, t, workdir)
        seed_workdir_from_fixture(t, workdir)

        # Build env_overrides from --env KEY=VAL pairs + --vendor shortcut.
        env_overrides: dict[str, str] = {}
        for pair in env or []:
            if "=" not in pair:
                console.print(
                    f"[red]--env requires KEY=VALUE, got {pair!r}[/red]"
                )
                raise typer.Exit(2)
            k, _, v = pair.partition("=")
            env_overrides[k.strip()] = v
        if vendor:
            from ab_harness.models import vendor_base_url

            env_overrides.setdefault("ANTHROPIC_BASE_URL", vendor_base_url(vendor))
            env_overrides.setdefault("ANTHROPIC_MODEL", model)

        runner_obj = _make_runner(
            runner,
            model,
            api_key=api_key,
            base_url=base_url,
            system_prompt=system_prompt,
            effort=effort,
            env_overrides=env_overrides or None,
        )
        runner_obj.prepare(materialized)

        traj_path = run_dir / "trajectory.jsonl"
        with TrajectoryWriter(traj_path) as writer:
            try:
                runner_obj.run_task(t, writer, workdir=workdir)
            finally:
                runner_obj.cleanup()

        verdicts = run_scorer_chain(t, traj_path, workdir, mode="run")
        splice_scorer_events(traj_path, verdicts)

        scores = _scores_payload(
            run_id=run_id,
            task_id=t.id,
            model=model,
            tier=tier_enum.value,
            dataset_version=dataset_version,
            verdicts=verdicts,
            task=t,
        )
        with (run_dir / SCORES_FILE).open("w", encoding="utf-8") as fh:
            json.dump(scores, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

        ScoresFile.model_validate(scores)

        finished_at = datetime.now(UTC).isoformat()
        metadata = {
            "run_id": run_id,
            "task_id": t.id,
            "model": model,
            "tier": tier_enum.value,
            "tier_hash": materialized.tier_hash,
            "dataset_version": dataset_version,
            "harness": runner_obj.version(),
            "started_at": started_at,
            "finished_at": finished_at,
            "status": "completed",
            "prompt_template_hash": None,
        }
        write_metadata(run_dir / "metadata.yaml", metadata)

        ok = bool(scores["pass"])
        overall_ok = overall_ok and ok
        marker = "[green]pass[/green]" if ok else "[red]fail[/red]"
        console.print(
            f"{marker} {t.id} tier={tier_enum.value} score={scores['total_score']:.3f} -> {run_dir}"
        )

    if not overall_ok:
        raise typer.Exit(1)
