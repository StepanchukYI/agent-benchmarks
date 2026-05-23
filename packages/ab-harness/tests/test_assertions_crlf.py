"""Tests for the CRLF-normalization relaxation in `workdir_file_preserves_crlf`
and `workdir_file_content_equals` assertions (B3 fix).

Before B3: both assertions required byte-exact CRLF preservation, so any model
that output LF line endings received a universal fail even when the textual
content was correct.

After B3: both assertions accept LF-only output when the content (normalized
CRLF→LF) matches the expected value. CRLF-preserving output still passes
(back-compat). Content mismatches still fail correctly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ab_harness.scorers.assertions import run_assertion_chain

# ---------------------------------------------------------------------------
# Helpers — minimal trajectory + single-assertion runner.
# ---------------------------------------------------------------------------

def _events() -> list[dict]:
    return [
        {"event": "run_start"},
        {"event": "turn", "idx": 0, "role": "assistant", "model_output": "done",
         "tool_calls": [], "tool_returns": []},
        {"event": "run_end"},
    ]


def _run_one(tmp_path: Path, kind: str, params: dict[str, Any]) -> tuple[bool, dict]:
    """Run a single assertion kind against tmp_path; return (ok, detail)."""
    verdict = run_assertion_chain(
        "x", _events(), tmp_path, None, [dict(params, kind=kind)]
    )
    entry = verdict.detail["assertions"][0]
    return entry["ok"], entry["detail"]


# ---------------------------------------------------------------------------
# workdir_file_preserves_crlf — three cases required by the task spec.
# ---------------------------------------------------------------------------

def test_preserves_crlf_lf_output_with_matching_content_passes(tmp_path: Path) -> None:
    """Case (a): expected CRLF, actual LF, same content → PASSES.

    This is the core relaxation: a model that writes LF line endings but
    produces the correct textual content should not fail the task.
    The detail.mode must be 'content_match_lf_normalized'.
    """
    expected = "line one\r\nline TWO\r\nline three\r\nline four\r\n"
    # Agent output: correct content but LF endings (the common model behaviour).
    (tmp_path / "notes.txt").write_bytes(b"line one\nline TWO\nline three\nline four\n")

    ok, detail = _run_one(
        tmp_path,
        "workdir_file_preserves_crlf",
        {"path": "notes.txt", "content": expected, "encoding": "utf-8"},
    )

    assert ok, f"Expected assertion to PASS but it failed. detail={detail}"
    assert detail.get("mode") == "content_match_lf_normalized", (
        f"Expected mode='content_match_lf_normalized', got {detail.get('mode')!r}"
    )


def test_preserves_crlf_lf_output_with_different_content_fails(tmp_path: Path) -> None:
    """Case (b): expected CRLF, actual LF, content differs → FAILS.

    Normalization must not paper over a genuine content mismatch (e.g. wrong
    word changed, missing line).
    """
    expected = "line one\r\nline TWO\r\nline three\r\nline four\r\n"
    # Agent wrote wrong replacement ("line 2" instead of "line TWO").
    (tmp_path / "notes.txt").write_bytes(b"line one\nline 2\nline three\nline four\n")

    ok, detail = _run_one(
        tmp_path,
        "workdir_file_preserves_crlf",
        {"path": "notes.txt", "content": expected, "encoding": "utf-8"},
    )

    assert not ok, f"Expected assertion to FAIL but it passed. detail={detail}"


def test_preserves_crlf_crlf_output_passes(tmp_path: Path) -> None:
    """Case (c): expected CRLF, actual CRLF, content matches → PASSES (back-compat).

    A model that correctly preserves CRLF must still pass. This must not regress.
    """
    expected = "line one\r\nline TWO\r\nline three\r\nline four\r\n"
    # Agent preserved CRLF — perfect output.
    (tmp_path / "notes.txt").write_bytes(
        b"line one\r\nline TWO\r\nline three\r\nline four\r\n"
    )

    ok, detail = _run_one(
        tmp_path,
        "workdir_file_preserves_crlf",
        {"path": "notes.txt", "content": expected, "encoding": "utf-8"},
    )

    assert ok, f"Expected CRLF-preserved output to PASS but it failed. detail={detail}"


# ---------------------------------------------------------------------------
# workdir_file_content_equals — same three cases via the content_equals path
# (this is the assertion actually fired by `crlf_preserved_diff` for L0_012).
# ---------------------------------------------------------------------------

def test_content_equals_lf_output_with_crlf_expected_passes(tmp_path: Path) -> None:
    """LF-output file matches CRLF-expected content after normalization → PASSES.

    This is the primary fix for L0_012: models output \\n, expected string has
    \\r\\n, but the texts are otherwise identical — should not fail.
    """
    expected = "line one\r\nline TWO\r\nline three\r\nline four\r\n"
    (tmp_path / "notes.txt").write_bytes(b"line one\nline TWO\nline three\nline four\n")

    ok, detail = _run_one(
        tmp_path,
        "workdir_file_content_equals",
        {"path": "notes.txt", "content": expected, "encoding": "utf-8"},
    )

    assert ok, f"Expected PASS (LF matches CRLF content) but failed. detail={detail}"
    assert detail.get("mode") == "content_match_lf_normalized", (
        f"Expected mode='content_match_lf_normalized', got {detail.get('mode')!r}"
    )


def test_content_equals_lf_output_different_content_fails(tmp_path: Path) -> None:
    """LF-output with wrong text → FAILS even after normalization."""
    expected = "line one\r\nline TWO\r\nline three\r\nline four\r\n"
    (tmp_path / "notes.txt").write_bytes(b"line one\nline 2\nline three\nline four\n")

    ok, detail = _run_one(
        tmp_path,
        "workdir_file_content_equals",
        {"path": "notes.txt", "content": expected, "encoding": "utf-8"},
    )

    assert not ok, f"Expected FAIL (wrong content) but it passed. detail={detail}"


def test_content_equals_crlf_output_exact_match_passes(tmp_path: Path) -> None:
    """Exact byte match (CRLF in, CRLF out) still passes via the fast path."""
    expected = "line one\r\nline TWO\r\nline three\r\nline four\r\n"
    (tmp_path / "notes.txt").write_bytes(
        b"line one\r\nline TWO\r\nline three\r\nline four\r\n"
    )

    ok, detail = _run_one(
        tmp_path,
        "workdir_file_content_equals",
        {"path": "notes.txt", "content": expected, "encoding": "utf-8"},
    )

    assert ok, f"Expected exact-match PASS but failed. detail={detail}"
    # Exact match takes the fast path; mode may be 'exact' or 'content_match_lf_normalized'.
    assert detail.get("mode") in {"exact", "content_match_lf_normalized"}, (
        f"Unexpected mode: {detail.get('mode')!r}"
    )


# ---------------------------------------------------------------------------
# Legacy back-compat: workdir_file_preserves_crlf without expected content.
# ---------------------------------------------------------------------------

def test_preserves_crlf_legacy_no_content_crlf_file_passes(tmp_path: Path) -> None:
    """Without expected content, CRLF-containing file passes (legacy behaviour)."""
    (tmp_path / "f.txt").write_bytes(b"k=v\r\n")
    ok, detail = _run_one(tmp_path, "workdir_file_preserves_crlf", {"path": "f.txt"})
    assert ok
    assert detail.get("mode") == "crlf_preserved"


def test_preserves_crlf_legacy_no_content_lf_file_fails(tmp_path: Path) -> None:
    """Without expected content, LF-only file fails (legacy behaviour preserved)."""
    (tmp_path / "f.txt").write_bytes(b"k=v\n")
    ok, _detail = _run_one(tmp_path, "workdir_file_preserves_crlf", {"path": "f.txt"})
    assert not ok
