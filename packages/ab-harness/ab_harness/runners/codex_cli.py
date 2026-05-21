"""Codex CLI adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ab_harness.runners.base import BaseRunner

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


class CodexCLIRunner(BaseRunner):
    def name(self) -> str:
        return "codex-cli"

    def version(self) -> str:
        raise NotImplementedError

    def prepare(self, tier_manifest: Any) -> None:
        raise NotImplementedError

    def run_task(self, task: Any, trajectory_writer: TrajectoryWriter) -> Any:
        raise NotImplementedError

    def cleanup(self) -> None:
        raise NotImplementedError
