"""Deterministic scorers: file_diff and exec.

Both expose a callable that accepts `mode="run"` (live workdir) or
`mode="replay"` (trajectory-only). Replay reconstructs the relevant
final state from `turn.vault_state_diff` + tool_returns where it can.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import replay_unsupported, score_to_verdict


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _truncate(s: str, limit: int = 200) -> str:
    return s if len(s) <= limit else s[:limit] + "...[truncated]"


def _match_expected(
    actual_bytes: bytes | None,
    expected: str | dict[str, Any],
) -> tuple[bool, str]:
    if actual_bytes is None:
        return False, "missing"

    if isinstance(expected, str):
        actual = actual_bytes.decode("utf-8", errors="replace")
        if actual == expected:
            return True, ""
        return False, f"expected={_truncate(expected)!r} actual={_truncate(actual)!r}"

    if isinstance(expected, dict):
        if "sha256" in expected:
            got = _sha256_bytes(actual_bytes)
            want = expected["sha256"]
            if got == want:
                return True, ""
            return False, f"sha256 mismatch want={want} got={got}"
        if "content" in expected:
            return _match_expected(actual_bytes, expected["content"])
        return False, f"unsupported expected spec keys={list(expected.keys())}"

    return False, f"unsupported expected type={type(expected).__name__}"


def file_diff_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    expected: dict[str, Any] | None = None,
    must_be_absent: Iterable[str] | None = None,
    **_: Any,
) -> ScorerVerdict:
    name = "file_diff"
    kind = ScorerKind.deterministic
    expected = expected or {}
    must_be_absent = list(must_be_absent or [])

    if mode == "replay":
        if trajectory_path is None:
            return replay_unsupported(name, kind, "trajectory_path required for replay")
        return _file_diff_replay(trajectory_path, expected, must_be_absent)

    if workdir is None:
        if trajectory_path is not None:
            return _file_diff_replay(trajectory_path, expected, must_be_absent)
        return replay_unsupported(name, kind, "workdir or trajectory_path required")

    return _file_diff_run(workdir, expected, must_be_absent)


def _file_diff_run(
    workdir: Path,
    expected: dict[str, Any],
    must_be_absent: list[str],
) -> ScorerVerdict:
    differing: list[dict[str, str]] = []
    matched = 0
    total = len(expected) + len(must_be_absent)

    for rel_path, exp in expected.items():
        target = workdir / rel_path
        actual_bytes = target.read_bytes() if target.exists() and target.is_file() else None
        ok, reason = _match_expected(actual_bytes, exp)
        if ok:
            matched += 1
        else:
            differing.append({"path": rel_path, "reason": reason})

    for rel_path in must_be_absent:
        target = workdir / rel_path
        if not target.exists():
            matched += 1
        else:
            differing.append({"path": rel_path, "reason": "should be absent but exists"})

    score = (matched / total) if total else 1.0
    ok = not differing
    detail: dict[str, Any] = {"matched": matched, "total": total, "differing": differing[:20]}
    return score_to_verdict("file_diff", ScorerKind.deterministic, ok, score, detail)


def _replay_final_state(trajectory_path: Path) -> dict[str, str]:
    created: set[str] = set()
    modified: set[str] = set()
    deleted: set[str] = set()
    content_by_path: dict[str, str] = {}

    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("event") != "turn":
                continue
            diff = ev.get("vault_state_diff") or {}
            for p in diff.get("created", []) or []:
                created.add(p)
                deleted.discard(p)
            for p in diff.get("modified", []) or []:
                modified.add(p)
                deleted.discard(p)
            for p in diff.get("deleted", []) or []:
                deleted.add(p)
                created.discard(p)
                modified.discard(p)
                content_by_path.pop(p, None)

            for ret in ev.get("tool_returns", []) or []:
                if not isinstance(ret, dict):
                    continue
                path = ret.get("path")
                content = ret.get("content")
                if isinstance(path, str) and isinstance(content, str):
                    content_by_path[path] = content

    return content_by_path


def _file_diff_replay(
    trajectory_path: Path,
    expected: dict[str, Any],
    must_be_absent: list[str],
) -> ScorerVerdict:
    created: set[str] = set()
    modified: set[str] = set()
    deleted: set[str] = set()
    content_by_path: dict[str, str] = {}

    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("event") != "turn":
                continue
            diff = ev.get("vault_state_diff") or {}
            for p in diff.get("created", []) or []:
                created.add(p)
                deleted.discard(p)
            for p in diff.get("modified", []) or []:
                modified.add(p)
                deleted.discard(p)
            for p in diff.get("deleted", []) or []:
                deleted.add(p)
                created.discard(p)
                modified.discard(p)
                content_by_path.pop(p, None)
            for ret in ev.get("tool_returns", []) or []:
                if not isinstance(ret, dict):
                    continue
                p = ret.get("path")
                c = ret.get("content")
                if isinstance(p, str) and isinstance(c, str):
                    content_by_path[p] = c

    differing: list[dict[str, str]] = []
    matched = 0
    total = len(expected) + len(must_be_absent)

    for rel_path, exp in expected.items():
        if rel_path in deleted:
            differing.append({"path": rel_path, "reason": "deleted in trajectory"})
            continue
        content = content_by_path.get(rel_path)
        if content is None:
            if rel_path in created or rel_path in modified:
                differing.append({"path": rel_path, "reason": "content not reconstructable from trajectory"})
            else:
                differing.append({"path": rel_path, "reason": "missing"})
            continue
        ok, reason = _match_expected(content.encode("utf-8"), exp)
        if ok:
            matched += 1
        else:
            differing.append({"path": rel_path, "reason": reason})

    for rel_path in must_be_absent:
        if rel_path in deleted or (rel_path not in created and rel_path not in modified):
            matched += 1
        else:
            differing.append({"path": rel_path, "reason": "should be absent but appears in trajectory"})

    score = (matched / total) if total else 1.0
    ok = not differing
    detail: dict[str, Any] = {"matched": matched, "total": total, "differing": differing[:20], "mode": "replay"}
    return score_to_verdict("file_diff", ScorerKind.deterministic, ok, score, detail)


def exec_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    cmd: list[str] | None = None,
    cwd: str | None = None,
    timeout: float = 60.0,
    expected_exit: int = 0,
    env: dict[str, str] | None = None,
    **_: Any,
) -> ScorerVerdict:
    name = "exec"
    kind = ScorerKind.deterministic

    if mode == "replay":
        if trajectory_path is None:
            return replay_unsupported(name, kind, "trajectory_path required for replay")
        return _exec_replay(trajectory_path, cmd or [], expected_exit)

    if workdir is None:
        if trajectory_path is not None:
            return _exec_replay(trajectory_path, cmd or [], expected_exit)
        return replay_unsupported(name, kind, "workdir or trajectory_path required")

    if not cmd:
        return score_to_verdict(name, kind, False, 0.0, {"error": "cmd is required"})

    run_cwd = workdir / cwd if cwd else workdir
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(run_cwd),
            capture_output=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return score_to_verdict(
            name,
            kind,
            False,
            0.0,
            {"error": "timeout", "timeout": timeout, "stdout": _truncate((exc.stdout or b"").decode("utf-8", errors="replace"), 1024)},
        )
    except FileNotFoundError as exc:
        return score_to_verdict(name, kind, False, 0.0, {"error": f"command not found: {exc}"})

    combined = (proc.stdout or b"") + (proc.stderr or b"")
    ok = proc.returncode == expected_exit
    detail: dict[str, Any] = {
        "exit_code": proc.returncode,
        "expected_exit": expected_exit,
        "output_head": _truncate(combined.decode("utf-8", errors="replace"), 1024),
    }
    return score_to_verdict(name, kind, ok, 1.0 if ok else 0.0, detail)


def _exec_replay(
    trajectory_path: Path,
    cmd: list[str],
    expected_exit: int,
) -> ScorerVerdict:
    name = "exec"
    kind = ScorerKind.deterministic

    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("event") != "turn":
                continue
            for ret in ev.get("tool_returns", []) or []:
                if not isinstance(ret, dict):
                    continue
                ret_cmd = ret.get("cmd")
                if cmd and ret_cmd != cmd:
                    continue
                if "exit_code" not in ret:
                    continue
                exit_code = ret.get("exit_code")
                output = ret.get("stdout", "") + ret.get("stderr", "")
                ok = exit_code == expected_exit
                detail = {
                    "exit_code": exit_code,
                    "expected_exit": expected_exit,
                    "output_head": _truncate(str(output), 1024),
                    "mode": "replay",
                }
                return score_to_verdict(name, kind, ok, 1.0 if ok else 0.0, detail)

    return replay_unsupported(name, kind, "no matching tool_return with exit_code in trajectory")


def schema_validator_scorer(*args: Any, **kwargs: Any) -> ScorerVerdict:
    from ab_harness.scorers.schema import schema_scorer

    return schema_scorer(*args, **kwargs)
