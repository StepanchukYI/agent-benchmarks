"""Privacy auto-scrub — scrub_text / scrub_file / scrub_run_dir / scrub_trajectory."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from ab_sdk.scrub import (
    ScrubPattern,
    load_scrub_patterns,
    scrub_file,
    scrub_run_dir_complete,
    scrub_text,
    scrub_trajectory,
)


def _pat(id: str, regex: str, replacement: str) -> ScrubPattern:
    return ScrubPattern(
        id=id,
        description="",
        regex=re.compile(regex),
        replacement=replacement,
        severity="medium",
    )


def test_scrub_text_replaces_and_reports_hits() -> None:
    patterns = [_pat("home", r"/Users/alice", "/home/scrubbed")]
    text = "open /Users/alice/notes/x.txt and /Users/alice/y.txt"
    out, hits = scrub_text(text, patterns)
    assert out == "open /home/scrubbed/notes/x.txt and /home/scrubbed/y.txt"
    assert len(hits) == 2
    assert all(h.pattern_id == "home" for h in hits)


def test_scrub_text_no_match_returns_text_unchanged() -> None:
    patterns = [_pat("home", r"/Users/alice", "/home/scrubbed")]
    text = "clean text"
    out, hits = scrub_text(text, patterns)
    assert out == "clean text"
    assert hits == []


def test_scrub_text_applies_patterns_in_order() -> None:
    """First pattern's replacement is visible to the second pattern."""
    patterns = [
        _pat("a", r"foo", "bar"),
        _pat("b", r"bar", "baz"),
    ]
    out, hits = scrub_text("foo and foo", patterns)
    assert out == "baz and baz"
    assert [h.pattern_id for h in hits] == ["a", "a", "b", "b"]


def test_scrub_file_writes_in_place(tmp_path: Path) -> None:
    f = tmp_path / "leak.txt"
    f.write_text("path=/Users/alice/x\n", encoding="utf-8")
    patterns = [_pat("home", r"/Users/alice", "/home/scrubbed")]
    hits = scrub_file(f, patterns)
    assert len(hits) == 1
    assert f.read_text(encoding="utf-8") == "path=/home/scrubbed/x\n"


def test_scrub_file_dry_run_does_not_write(tmp_path: Path) -> None:
    f = tmp_path / "leak.txt"
    original = "path=/Users/alice/x\n"
    f.write_text(original, encoding="utf-8")
    patterns = [_pat("home", r"/Users/alice", "/home/scrubbed")]
    hits = scrub_file(f, patterns, dry_run=True)
    assert len(hits) == 1
    assert f.read_text(encoding="utf-8") == original


def test_scrub_file_skips_binary_suffix(tmp_path: Path) -> None:
    f = tmp_path / "leak.pyc"
    f.write_bytes(b"\x00/Users/alice\x00")
    patterns = [_pat("home", r"/Users/alice", "/home/scrubbed")]
    assert scrub_file(f, patterns) == []
    # File untouched
    assert b"/Users/alice" in f.read_bytes()


def test_scrub_trajectory_preserves_jsonl_validity(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    lines = [
        {"event": "run_start", "run_id": "r1", "user_home": "/Users/alice/runs/r1"},
        {"event": "turn", "idx": 0, "model_output": "wrote /Users/alice/x.txt"},
        {"event": "run_end", "status": "completed"},
    ]
    traj.write_text(
        "".join(json.dumps(line) + "\n" for line in lines),
        encoding="utf-8",
    )

    patterns = [_pat("home", r"/Users/alice", "/home/scrubbed")]
    result = scrub_trajectory(traj, patterns)
    assert result["hits_total"] == 2
    assert result["by_pattern"]["home"] == 2

    # File still valid JSONL after scrub
    reread = [json.loads(line) for line in traj.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert reread[0]["user_home"] == "/home/scrubbed/runs/r1"
    assert reread[1]["model_output"] == "wrote /home/scrubbed/x.txt"


def test_scrub_trajectory_passes_through_malformed_lines(tmp_path: Path) -> None:
    traj = tmp_path / "bad.jsonl"
    traj.write_text(
        '{"event": "run_start"}\n'
        "not json at all\n"
        '{"event": "run_end"}\n',
        encoding="utf-8",
    )
    patterns = [_pat("home", r"/Users/alice", "/home/scrubbed")]
    result = scrub_trajectory(traj, patterns)
    assert result["lines"] == 3
    assert result["hits_total"] == 0
    # Bad line preserved
    assert "not json at all" in traj.read_text(encoding="utf-8")


def test_scrub_run_dir_complete_combined_summary(tmp_path: Path) -> None:
    run = tmp_path / "20260521T120000Z-run-abc"
    (run / "workdir").mkdir(parents=True)
    (run / "trajectory.jsonl").write_text(
        json.dumps({"event": "turn", "out": "/Users/alice/x"}) + "\n",
        encoding="utf-8",
    )
    (run / "scores.json").write_text(
        json.dumps({"path": "/Users/alice/result"}),
        encoding="utf-8",
    )
    (run / "workdir" / "notes.txt").write_text(
        "ref /Users/alice/notes.txt",
        encoding="utf-8",
    )

    patterns = [_pat("home", r"/Users/alice", "/home/scrubbed")]
    summary = scrub_run_dir_complete(run, patterns)
    assert summary["hits_total"] >= 3
    assert summary["by_pattern"]["home"] >= 3
    # Each surface scrubbed
    assert "/Users/alice" not in (run / "scores.json").read_text(encoding="utf-8")
    assert "/Users/alice" not in (run / "workdir" / "notes.txt").read_text(encoding="utf-8")
    assert "/Users/alice" not in (run / "trajectory.jsonl").read_text(encoding="utf-8")


def test_load_scrub_patterns_skips_detect_only(tmp_path: Path) -> None:
    """Patterns without scrub_replacement aren't returned by load_scrub_patterns."""
    patterns_file = tmp_path / "p.yaml"
    patterns_file.write_text(
        """
patterns:
  - id: with-replacement
    regex: "/Users/alice"
    severity: high
    scrub_replacement: "/home/scrubbed"
  - id: detect-only
    regex: "AKIA[0-9A-Z]{16}"
    severity: high
""",
        encoding="utf-8",
    )
    loaded = load_scrub_patterns(patterns_file)
    assert [p.id for p in loaded] == ["with-replacement"]


def test_load_scrub_patterns_skips_bad_regex(tmp_path: Path) -> None:
    patterns_file = tmp_path / "p.yaml"
    patterns_file.write_text(
        """
patterns:
  - id: bad-regex
    regex: "[unclosed"
    severity: medium
    scrub_replacement: "fixed"
  - id: good-regex
    regex: "/Users/alice"
    severity: high
    scrub_replacement: "/home/scrubbed"
""",
        encoding="utf-8",
    )
    loaded = load_scrub_patterns(patterns_file)
    assert [p.id for p in loaded] == ["good-regex"]


def test_real_patterns_yaml_loads(tmp_path: Path) -> None:
    """End-to-end smoke against the real docs/privacy-patterns.yaml."""
    repo_root = Path(__file__).resolve().parents[3]
    real = repo_root / "docs" / "privacy-patterns.yaml"
    if not real.exists():
        pytest.skip("privacy-patterns.yaml not in checkout (CI shouldn't hit this)")
    loaded = load_scrub_patterns(real)
    ids = {p.id for p in loaded}
    # Patterns that ship with replacements (auto-fixable).
    assert "email-real" in ids
    assert "maintainer-home-path" in ids
    # Detect-only (no replacement) — must NOT load.
    assert "aws-access-key-id" not in ids
    assert "github-token" not in ids
