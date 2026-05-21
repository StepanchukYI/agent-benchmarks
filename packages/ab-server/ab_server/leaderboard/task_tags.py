"""Task-tag lookup for sensitivity-aware leaderboard filtering.

Sensitivity tags are declared on each task YAML's `tags:` list (see
`docs/result-sensitivity-axes.md` for the 8 axes Track B applied to
L0). The leaderboard endpoint accepts `?include_task_tags=` /
`?exclude_task_tags=` query params; this module resolves task_id →
tag set without re-parsing YAMLs on every request.

Cache strategy:

* Lazy load on first call. ab-datasets is a workspace dep so the
  YAMLs live next to the server in dev; in prod the AB_DATASETS_ROOT
  env (or the discovered `ab_datasets` package data dir) points at
  them.
* The map is rebuilt only when ``invalidate_task_tags_cache()`` is
  called explicitly — task lists are append-only in normal operation,
  so an unbounded restart-survives cache is fine.
* Unknown task_ids resolve to the empty set (no-op for filtering).
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import yaml

_log = logging.getLogger(__name__)

# (task_id) -> frozenset(tags)
_TASK_TAG_CACHE: dict[str, frozenset[str]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LOADED = False


def _candidate_dataset_roots() -> list[Path]:
    """Find where the task YAMLs might live.

    Search order:
        1. AB_DATASETS_ROOT env override.
        2. ab_datasets package installed in the active venv.
        3. checkout-relative fallback (packages/ab-datasets/ab_datasets/).
    """
    import os

    roots: list[Path] = []
    env_root = os.environ.get("AB_DATASETS_ROOT")
    if env_root:
        roots.append(Path(env_root))
    try:
        import ab_datasets  # type: ignore[import-not-found]

        roots.append(Path(ab_datasets.__file__).resolve().parent)
    except ImportError:
        pass
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "packages" / "ab-datasets" / "ab_datasets"
        if candidate.exists():
            roots.append(candidate)
            break
    return roots


def _load_tag_map() -> dict[str, frozenset[str]]:
    """Walk every yaml under known dataset roots and build {task_id: tags}.

    Lenient — tasks without `id` or `tags` are skipped quietly.
    """
    out: dict[str, frozenset[str]] = {}
    for root in _candidate_dataset_roots():
        if not root.exists():
            continue
        for yml in root.rglob("*.yaml"):
            # Skip non-task fixtures (manifests, schemas, etc.)
            name = yml.name
            if name in {"manifest.yaml", ".github.yaml"}:
                continue
            try:
                raw = yaml.safe_load(yml.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            if not isinstance(raw, dict):
                continue
            task_id = raw.get("id")
            if not task_id or not isinstance(task_id, str):
                continue
            tags = raw.get("tags") or []
            if not isinstance(tags, list):
                continue
            out[task_id] = frozenset(str(t) for t in tags if isinstance(t, str))
    return out


def _ensure_loaded() -> None:
    global _CACHE_LOADED
    if _CACHE_LOADED:
        return
    with _CACHE_LOCK:
        if _CACHE_LOADED:
            return
        _TASK_TAG_CACHE.update(_load_tag_map())
        _CACHE_LOADED = True
        _log.info("task-tag cache loaded: %d task ids", len(_TASK_TAG_CACHE))


def tags_for(task_id: str) -> frozenset[str]:
    """Return the tag set for a task. Empty if unknown."""
    _ensure_loaded()
    return _TASK_TAG_CACHE.get(task_id, frozenset())


def all_known_tags() -> frozenset[str]:
    """Every tag declared on any known task. Useful for the FE picker."""
    _ensure_loaded()
    out: set[str] = set()
    for tags in _TASK_TAG_CACHE.values():
        out.update(tags)
    return frozenset(out)


def task_matches_filters(
    task_id: str,
    *,
    include: frozenset[str] | None = None,
    exclude: frozenset[str] | None = None,
) -> bool:
    """Apply include/exclude tag filters.

    * `include`: task must have AT LEAST ONE of these tags (None / empty = pass).
    * `exclude`: task must have NONE of these tags (None / empty = pass).
    Unknown task_ids pass through (no tags → not excluded, but also not
    included if `include` is non-empty).
    """
    tags = tags_for(task_id)
    if include and not (tags & include):
        return False
    return not (exclude and (tags & exclude))


def invalidate_task_tags_cache() -> None:
    """Drop the cache. Next call to tags_for / all_known_tags reloads."""
    global _CACHE_LOADED
    with _CACHE_LOCK:
        _TASK_TAG_CACHE.clear()
        _CACHE_LOADED = False


__all__ = [
    "all_known_tags",
    "invalidate_task_tags_cache",
    "tags_for",
    "task_matches_filters",
]
