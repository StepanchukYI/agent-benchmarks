"""BaseRunner ABC — all model adapters normalize into the shared trajectory protocol."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


class BaseRunner(abc.ABC):
    """Adapter interface for a model + harness combination."""

    @abc.abstractmethod
    def name(self) -> str:
        """Stable runner identifier (e.g. 'claude-code-cli')."""

    @abc.abstractmethod
    def version(self) -> str:
        """Adapter or upstream-tool version string."""

    @abc.abstractmethod
    def prepare(self, tier_manifest: Any) -> None:
        """Materialize tier config and warm up the runner."""

    @abc.abstractmethod
    def run_task(self, task: Any, trajectory_writer: TrajectoryWriter) -> Any:
        """Execute a task; return a RunStatus."""

    @abc.abstractmethod
    def cleanup(self) -> None:
        """Tear down any resources allocated in prepare()."""
