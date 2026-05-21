from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import Task


def load_task(path: str | Path) -> Task:
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return Task.model_validate(data)


def load_tasks(root: str | Path) -> list[Task]:
    r = Path(root)
    return [load_task(p) for p in sorted(r.rglob("*.yaml"))]
