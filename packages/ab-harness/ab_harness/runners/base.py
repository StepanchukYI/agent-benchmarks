"""BaseRunner ABC — all model adapters normalize into the shared trajectory protocol."""

from __future__ import annotations

import abc
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


def compose_system_prompt(sandbox_prompt: str, claude_md_text: str | None) -> str:
    """run_start.system_prompt_verbatim = sandbox guardrail + project CLAUDE.md.

    Captures everything the model saw as standing context (axis #11). With no
    materialized CLAUDE.md (e.g. T0 vanilla) the sandbox prompt is returned
    unchanged, so existing trajectories stay byte-identical.
    """
    if not claude_md_text:
        return sandbox_prompt
    return f"{sandbox_prompt}\n\n--- project CLAUDE.md ---\n{claude_md_text}"


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
    def run_task(
        self,
        task: Any,
        trajectory_writer: TrajectoryWriter,
        workdir: Path,
    ) -> Any:
        """Execute a task in `workdir`; return a RunStatus."""

    @abc.abstractmethod
    def cleanup(self) -> None:
        """Tear down any resources allocated in prepare()."""
