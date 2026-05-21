"""Locate tasks, fixtures, and tier roots inside the repo."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from ab_datasets.loaders import load_task
from ab_datasets.schemas import Task

_LAYER_DIR_BY_PREFIX = {
    "L0": "L0_foundation",
    "L1": "L1_memory",
    "L2": "L2_skills",
    "L3": "L3_domains",
    "L4": "L4_composite",
    "L5": "L5_evolved",
}


def repo_root(start: Path | None = None) -> Path:
    """Walk parents from start (or this file) until we find pyproject.toml."""
    here = Path(start) if start is not None else Path(__file__).resolve()
    if here.is_file():
        here = here.parent
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists() and (parent / "packages").is_dir():
            return parent
    raise RuntimeError("could not locate repo root containing pyproject.toml + packages/")


def datasets_root(start: Path | None = None) -> Path:
    return repo_root(start) / "packages" / "ab-datasets" / "ab_datasets"


def fixtures_root(start: Path | None = None) -> Path:
    return repo_root(start) / "packages" / "ab-datasets" / "fixtures"


def tier_root(start: Path | None = None) -> Path:
    return fixtures_root(start) / "config_tiers"


def discover_tasks(suite: str, *, single_task: str | None = None) -> list[Task]:
    """Resolve `suite` (e.g. L0_smoke, file-ops, L0_001) into a list of Task models."""
    ds = datasets_root()
    candidates: list[Path] = []

    if single_task:
        for layer_dir in ds.iterdir():
            if not layer_dir.is_dir():
                continue
            for p in layer_dir.rglob(f"{single_task}*.yaml"):
                candidates.append(p)
        if not candidates:
            raise FileNotFoundError(f"task not found: {single_task}")
        return [load_task(p) for p in sorted(set(candidates))]

    if suite.endswith("_smoke"):
        prefix = suite.split("_", 1)[0]
        layer_dir_name = _LAYER_DIR_BY_PREFIX.get(prefix)
        if layer_dir_name is None:
            raise ValueError(f"unknown suite prefix: {suite}")
        layer_dir = ds / layer_dir_name
        candidates = sorted(layer_dir.rglob("*.yaml"))
    else:
        for layer_dir in ds.iterdir():
            if not layer_dir.is_dir() or not layer_dir.name.startswith("L"):
                continue
            for p in sorted(layer_dir.rglob("*.yaml")):
                t = load_task(p)
                if t.suite == suite:
                    candidates.append(p)

    if not candidates:
        raise FileNotFoundError(f"no tasks matched suite: {suite}")

    return [load_task(p) for p in candidates]


def fixture_dir_for_task(task: Task) -> Path | None:
    """Resolve the task's `fixture_ref` path to an absolute dir, or None if missing."""
    if not task.fixture_ref:
        return None
    candidate = (fixtures_root().parent / task.fixture_ref).resolve()
    if candidate.exists():
        return candidate
    candidate2 = (fixtures_root() / task.fixture_ref).resolve()
    if candidate2.exists():
        return candidate2
    candidate3 = (repo_root() / task.fixture_ref).resolve()
    if candidate3.exists():
        return candidate3
    return None


def seed_workdir_from_fixture(task: Task, workdir: Path) -> Iterable[str]:
    """Copy the task's fixture directory contents into workdir. Returns copied relpaths."""
    import shutil

    src = fixture_dir_for_task(task)
    copied: list[str] = []
    if src is None or not src.is_dir():
        return copied
    for entry in src.rglob("*"):
        if entry.name == ".gitkeep":
            continue
        rel = entry.relative_to(src)
        target = workdir / rel
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, target)
            copied.append(str(rel))
    return copied
