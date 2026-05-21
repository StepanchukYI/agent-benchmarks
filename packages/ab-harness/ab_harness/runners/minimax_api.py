"""MiniMax adapter — OpenAI-compatible endpoint via httpx."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from ab_harness.runners.base import BaseRunner

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


class MiniMaxAPIRunner(BaseRunner):
    def __init__(self, base_url: str | None = None, api_key: str | None = None) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self._client: httpx.Client | None = None

    def name(self) -> str:
        return "minimax-api"

    def version(self) -> str:
        raise NotImplementedError

    def prepare(self, tier_manifest: Any) -> None:
        raise NotImplementedError

    def run_task(self, task: Any, trajectory_writer: TrajectoryWriter, workdir: Path) -> Any:
        raise NotImplementedError

    def cleanup(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
