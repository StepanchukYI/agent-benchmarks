"""Insert scorer events between the final turn and run_end, preserving §6 order."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerVerdict


def splice_scorer_events(path: str | Path, verdicts: list[ScorerVerdict]) -> None:
    """Read a trajectory.jsonl, drop the run_end, append scorer events, re-append run_end.

    Used by the `ab run` orchestrator after `run_scorer_chain` produces verdicts.
    Spec §6 invariant: scorer events appear strictly after the last turn and
    before run_end.
    """
    p = Path(path)
    events: list[dict[str, Any]] = []
    with p.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            events.append(json.loads(line))

    run_end_events = [e for e in events if e.get("event") == "run_end"]
    if not run_end_events:
        return
    run_end = run_end_events[-1]
    non_end = [e for e in events if e.get("event") != "run_end"]

    scorer_events: list[dict[str, Any]] = []
    for v in verdicts:
        payload = v.model_dump(mode="json", by_alias=True)
        payload["event"] = "scorer"
        scorer_events.append(payload)

    with p.open("w", encoding="utf-8") as fh:
        for ev in non_end:
            fh.write(json.dumps(ev, ensure_ascii=False))
            fh.write("\n")
        for ev in scorer_events:
            fh.write(json.dumps(ev, ensure_ascii=False))
            fh.write("\n")
        fh.write(json.dumps(run_end, ensure_ascii=False))
        fh.write("\n")
