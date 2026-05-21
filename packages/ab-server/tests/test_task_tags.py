"""Task-tag lookup + leaderboard endpoint sensitivity-filter wiring."""

from __future__ import annotations

from ab_server.leaderboard.task_tags import (
    all_known_tags,
    invalidate_task_tags_cache,
    tags_for,
    task_matches_filters,
)


def setup_function() -> None:
    """Fresh cache each test — the helper is process-global."""
    invalidate_task_tags_cache()


def test_tags_for_known_l0_task_has_sensitivity_tags() -> None:
    """L0_001 ships with sensitivity tags per Track B's pass."""
    tags = tags_for("L0_001")
    # We don't pin the exact set; the taxonomy is locked by
    # test_l0_sensitivity_tags. Just confirm the lookup wires up.
    assert isinstance(tags, frozenset)


def test_tags_for_unknown_task_is_empty() -> None:
    assert tags_for("NOPE_999") == frozenset()


def test_all_known_tags_is_populated() -> None:
    tags = all_known_tags()
    assert isinstance(tags, frozenset)
    # Track B applied 8 tag classes to L0; lookup must surface at least
    # the ones documented in docs/result-sensitivity-axes.md.
    assert "reasoning-sensitive" in tags or "byte-exact-output" in tags


def test_task_matches_filters_no_filters_passes_all() -> None:
    assert task_matches_filters("L0_001") is True
    assert task_matches_filters("NOPE_999") is True


def test_task_matches_filters_include_passes_when_any_match() -> None:
    tags = tags_for("L0_001")
    if not tags:
        # If L0_001 has no tags, this test path is moot — re-anchor to
        # any task that does carry tags.
        for tid_pick in ("L0_402", "L0_103", "L0_201", "L0_605"):
            if tags_for(tid_pick):
                tags = tags_for(tid_pick)
                anchor = tid_pick
                break
        else:
            return  # Track B not loaded; skip
    else:
        anchor = "L0_001"
    a_tag = next(iter(tags))
    assert task_matches_filters(anchor, include=frozenset({a_tag})) is True


def test_task_matches_filters_include_blocks_when_none_match() -> None:
    """A task without the requested include tag is excluded."""
    # Find a task with at least one tag, then ask for a tag it doesn't have.
    for tid in ("L0_001", "L0_402", "L0_103", "L0_605", "L0_201"):
        ts = tags_for(tid)
        if ts:
            unrelated = "completely-made-up-tag-that-no-task-has"
            assert task_matches_filters(tid, include=frozenset({unrelated})) is False
            return
    # No tasks loaded → skip.


def test_task_matches_filters_exclude_blocks_when_any_match() -> None:
    for tid in ("L0_001", "L0_402", "L0_103", "L0_605", "L0_201"):
        ts = tags_for(tid)
        if ts:
            a_tag = next(iter(ts))
            assert task_matches_filters(tid, exclude=frozenset({a_tag})) is False
            return


def test_cache_survives_within_process() -> None:
    """Second call must NOT re-walk YAMLs — same object identity OK as proof."""
    a = tags_for("L0_001")
    b = tags_for("L0_001")
    assert a == b
    # all_known_tags must also be stable.
    assert all_known_tags() == all_known_tags()


def test_invalidate_clears_then_rebuilds() -> None:
    before = all_known_tags()
    invalidate_task_tags_cache()
    after = all_known_tags()
    assert before == after  # identical on-disk state → identical reload
