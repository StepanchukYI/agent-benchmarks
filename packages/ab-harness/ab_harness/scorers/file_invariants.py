"""Deterministic scorers for file invariants:

- `test_file_unchanged`: assert one or more files are byte-identical to the
  fixture version (i.e. the agent did not modify them). In replay mode,
  scan trajectory `tool_calls` for write-style tools (Write/Edit/MultiEdit/
  str_replace_editor) that target any of the protected paths.

- `readme_exact`: assert one or more files match expected literal content
  exactly. In replay mode, reconstruct the final content of each path from
  the last write-style `tool_call` and compare.

Both accept the same YAML config shape as `file_diff`:

    config:
      expected:
        <relative_path>: "<literal content>"

This shape is preferred (over `expected_path` / `expected_content`) because
the existing L0_004 and L0_005 task YAMLs already declare it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import replay_unsupported, score_to_verdict

# Tool names that materialize a file write in the trajectory.
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "str_replace_editor", "str_replace_based_edit_tool"}


def _truncate(s: str, limit: int = 200) -> str:
    return s if len(s) <= limit else s[:limit] + "...[truncated]"


def _extract_target_path(tc: dict[str, Any]) -> str | None:
    args = tc.get("args") or tc.get("input") or {}
    if not isinstance(args, dict):
        return None
    for key in ("file_path", "path", "target_file"):
        v = args.get(key)
        if isinstance(v, str) and v:
            return v
    return None


def _extract_final_content(tc: dict[str, Any]) -> str | None:
    """Best-effort: pull the post-write content from a tool_call's args.

    Supports Write (`content`), Edit (`new_string` replacing `old_string`),
    str_replace_editor (`new_str`/`file_text`).
    Returns None if we cannot reconstruct.
    """
    args = tc.get("args") or tc.get("input") or {}
    if not isinstance(args, dict):
        return None
    # Write-style: full content provided.
    for key in ("content", "file_text", "new_str"):
        v = args.get(key)
        if isinstance(v, str):
            return v
    return None


def _iter_turns(trajectory_path: Path):
    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") != "turn":
                continue
            yield ev


def _normalize_expected(expected: Any) -> dict[str, str]:
    """Accept either:
      - dict[path -> content]                       (L0_004, L0_005 YAML shape)
      - {"expected_path": str, "expected_content": str}  (alt shape from task spec)
    Returns dict[path -> content].
    """
    if isinstance(expected, dict) and expected:
        # check for alt single-file shape
        if "expected_path" in expected and "expected_content" in expected:
            return {str(expected["expected_path"]): str(expected["expected_content"])}
        out: dict[str, str] = {}
        for k, v in expected.items():
            if isinstance(v, str):
                out[str(k)] = v
            elif isinstance(v, dict) and "content" in v and isinstance(v["content"], str):
                out[str(k)] = v["content"]
        return out
    return {}


# ---------------------------------------------------------------------------
# test_file_unchanged
# ---------------------------------------------------------------------------


def test_file_unchanged_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    expected: dict[str, Any] | None = None,
    expected_path: str | None = None,
    expected_content: str | None = None,
    expected_sha256: str | None = None,
    **_: Any,
) -> ScorerVerdict:
    name = "test_file_unchanged"
    kind = ScorerKind.deterministic

    # Build a normalized {path: content} map from either the dict-shape
    # or the alt (expected_path, expected_content) shape.
    targets = _normalize_expected(expected)
    if not targets and expected_path is not None and expected_content is not None:
        targets = {expected_path: expected_content}

    # Allow sha256 single-path shape (task spec proposed it).
    sha_target: tuple[str, str] | None = None
    if not targets and expected_path is not None and expected_sha256 is not None:
        sha_target = (expected_path, expected_sha256)

    if not targets and sha_target is None:
        return score_to_verdict(
            name, kind, False, 0.0,
            {"error": "expected (dict path->content) or expected_path+expected_content required"},
        )

    if mode == "replay":
        if trajectory_path is None:
            return replay_unsupported(name, kind, "trajectory_path required for replay")
        return _test_file_unchanged_replay(trajectory_path, list(targets.keys()) or [sha_target[0]])

    if workdir is None:
        if trajectory_path is not None:
            return _test_file_unchanged_replay(trajectory_path, list(targets.keys()) or [sha_target[0]])
        return replay_unsupported(name, kind, "workdir or trajectory_path required")

    differing: list[dict[str, str]] = []
    matched = 0

    if sha_target is not None:
        import hashlib
        path, want_sha = sha_target
        target = workdir / path
        if not target.exists() or not target.is_file():
            differing.append({"path": path, "reason": "missing"})
        else:
            got = hashlib.sha256(target.read_bytes()).hexdigest()
            if got == want_sha:
                matched += 1
            else:
                differing.append({"path": path, "reason": f"sha256 mismatch want={want_sha} got={got}"})
        total = 1
    else:
        total = len(targets)
        for rel_path, want in targets.items():
            target = workdir / rel_path
            if not target.exists() or not target.is_file():
                differing.append({"path": rel_path, "reason": "missing"})
                continue
            actual = target.read_bytes().decode("utf-8", errors="replace")
            if actual == want:
                matched += 1
            else:
                differing.append({
                    "path": rel_path,
                    "reason": f"modified: expected={_truncate(want)!r} actual={_truncate(actual)!r}",
                })

    score = (matched / total) if total else 1.0
    ok = not differing
    return score_to_verdict(
        name, kind, ok, score,
        {"matched": matched, "total": total, "differing": differing[:20], "mode": "run"},
    )


def _test_file_unchanged_replay(
    trajectory_path: Path,
    protected_paths: list[str],
) -> ScorerVerdict:
    name = "test_file_unchanged"
    kind = ScorerKind.deterministic
    protected = set(protected_paths)
    saw_any_write_tool = False
    violations: list[dict[str, str]] = []

    for ev in _iter_turns(trajectory_path):
        for tc in ev.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tname = tc.get("name")
            if tname in _WRITE_TOOLS:
                saw_any_write_tool = True
                path = _extract_target_path(tc)
                if path is None:
                    continue
                # Normalize: match exact and basename to be robust against
                # absolute paths in tool args.
                norm = path
                if norm in protected:
                    violations.append({"path": norm, "tool": str(tname)})
                else:
                    base = norm.rsplit("/", 1)[-1]
                    for p in protected:
                        if p == base or p.endswith("/" + base) or norm.endswith("/" + p):
                            violations.append({"path": p, "tool": str(tname), "via": norm})
                            break

    if not saw_any_write_tool:
        # We can't conclude the file is unchanged if no tool info was recorded.
        return replay_unsupported(
            name, kind,
            "trajectory has no Write/Edit tool_calls; cannot determine if protected files were modified",
        )

    ok = not violations
    score = 1.0 if ok else 0.0
    return score_to_verdict(
        name, kind, ok, score,
        {"protected": sorted(protected), "violations": violations[:20], "mode": "replay"},
    )


# ---------------------------------------------------------------------------
# readme_exact
# ---------------------------------------------------------------------------


def readme_exact_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    expected: dict[str, Any] | None = None,
    expected_path: str | None = None,
    expected_content: str | None = None,
    **_: Any,
) -> ScorerVerdict:
    name = "readme_exact"
    kind = ScorerKind.deterministic

    targets = _normalize_expected(expected)
    if not targets and expected_path is not None and expected_content is not None:
        targets = {expected_path: expected_content}

    if not targets:
        return score_to_verdict(
            name, kind, False, 0.0,
            {"error": "expected (dict path->content) or expected_path+expected_content required"},
        )

    if mode == "replay":
        if trajectory_path is None:
            return replay_unsupported(name, kind, "trajectory_path required for replay")
        return _readme_exact_replay(trajectory_path, targets)

    if workdir is None:
        if trajectory_path is not None:
            return _readme_exact_replay(trajectory_path, targets)
        return replay_unsupported(name, kind, "workdir or trajectory_path required")

    differing: list[dict[str, str]] = []
    matched = 0
    total = len(targets)
    for rel_path, want in targets.items():
        target = workdir / rel_path
        if not target.exists() or not target.is_file():
            differing.append({"path": rel_path, "reason": "missing"})
            continue
        actual = target.read_bytes().decode("utf-8", errors="replace")
        if actual == want:
            matched += 1
        else:
            differing.append({
                "path": rel_path,
                "reason": f"expected={_truncate(want)!r} actual={_truncate(actual)!r}",
            })

    score = (matched / total) if total else 1.0
    ok = not differing
    return score_to_verdict(
        name, kind, ok, score,
        {"matched": matched, "total": total, "differing": differing[:20], "mode": "run"},
    )


def _readme_exact_replay(
    trajectory_path: Path,
    targets: dict[str, str],
) -> ScorerVerdict:
    name = "readme_exact"
    kind = ScorerKind.deterministic

    # Final content per path: last write wins. Track both via tool_calls
    # (which usually carry full content) and tool_returns (which sometimes do).
    final_content: dict[str, str] = {}
    saw_any_write = False
    unreconstructable: set[str] = set()

    for ev in _iter_turns(trajectory_path):
        for tc in ev.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            if tc.get("name") not in _WRITE_TOOLS:
                continue
            saw_any_write = True
            path = _extract_target_path(tc)
            if path is None:
                continue
            # Match either exact path or basename of an expected target.
            matched_key: str | None = None
            for k in targets:
                if path == k or path.endswith("/" + k):
                    matched_key = k
                    break
            if matched_key is None:
                continue
            content = _extract_final_content(tc)
            if content is None:
                unreconstructable.add(matched_key)
                continue
            final_content[matched_key] = content
            unreconstructable.discard(matched_key)

        # Fall back to tool_returns w/ {path, content}.
        for ret in ev.get("tool_returns") or []:
            if not isinstance(ret, dict):
                continue
            p = ret.get("path")
            c = ret.get("content")
            if isinstance(p, str) and isinstance(c, str):
                for k in targets:
                    if p == k or p.endswith("/" + k):
                        final_content[k] = c
                        unreconstructable.discard(k)
                        saw_any_write = True
                        break

    if not saw_any_write:
        return replay_unsupported(
            name, kind,
            "trajectory has no write-style tool_calls; cannot reconstruct final file content",
        )

    differing: list[dict[str, str]] = []
    matched = 0
    total = len(targets)
    for rel_path, want in targets.items():
        if rel_path in unreconstructable and rel_path not in final_content:
            return replay_unsupported(
                name, kind,
                f"final content for {rel_path!r} not reconstructable from trajectory",
            )
        actual = final_content.get(rel_path)
        if actual is None:
            differing.append({"path": rel_path, "reason": "no write found in trajectory"})
            continue
        if actual == want:
            matched += 1
        else:
            differing.append({
                "path": rel_path,
                "reason": f"expected={_truncate(want)!r} actual={_truncate(actual)!r}",
            })

    score = (matched / total) if total else 1.0
    ok = not differing
    return score_to_verdict(
        name, kind, ok, score,
        {"matched": matched, "total": total, "differing": differing[:20], "mode": "replay"},
    )
