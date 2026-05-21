"""Append-only JSONL writer for the trajectory protocol (build spec §6)."""

from __future__ import annotations

import json
from pathlib import Path
from types import TracebackType
from typing import Any

from pydantic import BaseModel


def _to_jsonable(payload: Any) -> dict[str, Any]:
    if isinstance(payload, BaseModel):
        return payload.model_dump(mode="json", by_alias=True)
    if isinstance(payload, dict):
        return payload
    raise TypeError(f"Unsupported trajectory payload type: {type(payload)!r}")


class TrajectoryWriter:
    """One-JSON-object-per-line writer for trajectory events."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")

    def __enter__(self) -> TrajectoryWriter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def _write_event(self, event: str, payload: Any) -> None:
        obj = _to_jsonable(payload)
        obj["event"] = event
        self._fh.write(json.dumps(obj, ensure_ascii=False, sort_keys=False))
        self._fh.write("\n")
        self._fh.flush()

    def write_run_start(self, payload: Any) -> None:
        self._write_event("run_start", payload)

    def write_turn(self, payload: Any) -> None:
        self._write_event("turn", payload)

    def write_scorer(self, payload: Any) -> None:
        self._write_event("scorer", payload)

    def write_run_end(self, payload: Any) -> None:
        self._write_event("run_end", payload)
