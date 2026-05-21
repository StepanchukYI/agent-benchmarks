"""Deterministic mock runner — emits a canned trajectory matching task acceptance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ab_harness.runners._vault_diff import diff, snapshot
from ab_harness.runners.base import BaseRunner

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


_DEFAULT_DATASET_VERSION = "ab-datasets==0.0.1"


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class MockRunner(BaseRunner):
    """Pretends to execute a task; lets the live scorers run against the workdir.

    The mock writes a minimal trajectory (run_start + 1 assistant turn + run_end)
    and leaves the workdir untouched. Scorers like privacy_check / state_diff
    still execute against the workdir; file-shaped scorers will report whatever
    the workdir contains. This is what we use to wire `ab run` end-to-end in
    tests without calling a real model.
    """

    def __init__(
        self,
        model: str = "mock-model",
        dataset_version: str = _DEFAULT_DATASET_VERSION,
        seed_fn: Any | None = None,
    ) -> None:
        self._model = model
        self._dataset_version = dataset_version
        self._seed_fn = seed_fn
        self._tier_manifest: Any | None = None

    def name(self) -> str:
        return "ab-mock"

    def version(self) -> str:
        return "ab-mock@0.0.1"

    def prepare(self, tier_manifest: Any) -> None:
        self._tier_manifest = tier_manifest

    def cleanup(self) -> None:
        return None

    def _tier_value(self) -> str:
        if self._tier_manifest is None:
            return "T0"
        tier = getattr(self._tier_manifest, "tier", None)
        return getattr(tier, "value", None) or (tier if isinstance(tier, str) else "T0")

    def _tier_hash(self) -> str | None:
        return getattr(self._tier_manifest, "tier_hash", None) or getattr(
            self._tier_manifest, "total_sha256", None
        )

    def run_task(
        self,
        task: Any,
        trajectory_writer: TrajectoryWriter,
        workdir: Path | None = None,
    ) -> Any:
        from ab_datasets.schemas import RunStatus

        if workdir is None:
            raise ValueError("workdir is required")
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        task_id = getattr(task, "id", None) or "unknown"
        started_at = _utc_now_iso()

        trajectory_writer.write_run_start(
            {
                "run_id": run_id,
                "task_id": task_id,
                "model": self._model,
                "harness": self.version(),
                "tier": self._tier_value(),
                "tier_hash": self._tier_hash(),
                "dataset_version": self._dataset_version,
                "prompt_template_hash": None,
                "started_at": started_at,
            }
        )

        before = snapshot(workdir)
        if callable(self._seed_fn):
            self._seed_fn(task, workdir)
        after = snapshot(workdir)
        vault_diff = diff(before, after)

        trajectory_writer.write_turn(
            {
                "idx": 0,
                "role": "assistant",
                "prompt_delta": None,
                "tool_calls": [],
                "tool_returns": [],
                "model_output": f"mock run for {task_id}",
                "vault_state_diff": vault_diff,
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
            }
        )

        trajectory_writer.write_run_end(
            {
                "finished_at": _utc_now_iso(),
                "status": "completed",
                "totals": {
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "latency_ms": 0,
                    "cost_usd": 0.0,
                    "score": 1.0,
                },
            }
        )
        return RunStatus.completed
