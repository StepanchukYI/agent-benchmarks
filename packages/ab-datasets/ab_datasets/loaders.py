from __future__ import annotations

from pathlib import Path

import yaml

from .schemas import Task


def load_task(path: Path) -> Task:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return Task.model_validate(data)


def load_tasks(root: Path) -> list[Task]:
    return [load_task(p) for p in sorted(root.rglob("*.yaml"))]
