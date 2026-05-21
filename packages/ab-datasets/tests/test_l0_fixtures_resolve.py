"""For every L0 task that declares a fixture_ref, the path must exist
on disk under packages/ab-datasets/. Catches typos and convention drift
the moment a task is added.

`fixture_ref` is resolved relative to `packages/ab-datasets/` per the
convention in `docs/adding-a-task.md` §3.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ab_datasets.schemas import Task

DATASETS_PKG = Path(__file__).resolve().parent.parent          # packages/ab-datasets
DATASETS_ROOT = DATASETS_PKG / "ab_datasets"
L0_DIR = DATASETS_ROOT / "L0_foundation"

L0_FILES: tuple[Path, ...] = tuple(sorted(L0_DIR.glob("*.yaml")))


def _load(path: Path) -> Task:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Task.model_validate(data)


def _ids(files):
    return [p.name for p in files]


def test_l0_has_tasks() -> None:
    assert L0_FILES, f"no L0 task files under {L0_DIR}"
    assert len(L0_FILES) >= 20, f"L0 backlog floor is 20 tasks, got {len(L0_FILES)}"


@pytest.mark.parametrize("path", L0_FILES, ids=_ids(L0_FILES))
def test_fixture_ref_resolves(path: Path) -> None:
    """If a task declares fixture_ref, the on-disk path must exist."""
    task = _load(path)
    if task.fixture_ref is None:
        pytest.skip(f"{task.id} has no fixture_ref (allowed for text-only tasks)")

    # Convention: fixture_ref starts with `fixtures/` and is rooted at packages/ab-datasets/
    assert task.fixture_ref.startswith("fixtures/"), (
        f"{task.id} fixture_ref={task.fixture_ref!r} does not start with `fixtures/`; "
        f"docs/adding-a-task.md §3 mandates the prefix"
    )
    target = DATASETS_PKG / task.fixture_ref
    assert target.exists(), (
        f"{task.id} fixture_ref={task.fixture_ref!r} → {target} does not exist; "
        f"create the fixture under packages/ab-datasets/{task.fixture_ref} or fix the path"
    )


@pytest.mark.parametrize("path", L0_FILES, ids=_ids(L0_FILES))
def test_fixture_ref_is_under_canonical_root(path: Path) -> None:
    """Each L0 fixture path is under one of the four canonical roots."""
    task = _load(path)
    if task.fixture_ref is None:
        pytest.skip(f"{task.id} has no fixture_ref")
    allowed_prefixes = (
        "fixtures/repos/",
        "fixtures/vault_snapshots/",
        "fixtures/mcp_mocks/",
        "fixtures/config_tiers/",
    )
    assert task.fixture_ref.startswith(allowed_prefixes), (
        f"{task.id} fixture_ref={task.fixture_ref!r} is not under any canonical root: "
        f"{allowed_prefixes}"
    )
