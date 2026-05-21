"""Assertion engine for Track-B deterministic scorers.

Track B's task YAMLs describe deterministic scorers as a *chain of assertions*
in `scorer.config.assertions`. Each entry has a `kind:` and kind-specific params.

This module:
  * defines a uniform AssertionFn signature,
  * registers small, obvious implementations for every assertion kind in use,
  * exposes `run_assertion_chain` which walks the list and produces a
    `ScorerVerdict` with `pass_=all(ok)` and `score=passed/total`.

Heavy lifting (iterating trajectory turns, extracting tool calls, etc.) lives
in shared helpers near the top of the file so each assertion stays tiny.
"""

from __future__ import annotations

import contextlib
import difflib
import json
import re
import tarfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict

from ab_harness.scorers._base import score_to_verdict

AssertionFn = Callable[
    [list[dict], "Path | None", "Path | None", dict],
    tuple[bool, dict],
]

# Single source of truth for an emoji codepoint sweep. We err on the side of
# completeness — matches the spec ranges + common dingbats/regional indicators.
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"  # symbols & pictographs, emoticons, supplemental
    "\U0001FA00-\U0001FAFF"  # symbols & pictographs extended-A
    "\U00002600-\U000027BF"  # misc symbols + dingbats
    "\U0001F100-\U0001F1FF"  # enclosed alphanumeric supplement (regional indicators)
    "\U00002300-\U000023FF"  # misc technical
    "\U0000FE0F"             # variation selector-16
    "]",
    flags=re.UNICODE,
)

# Treat ` ``` ` fences, **bold**, leading "# " or "- " markers as markdown.
_MD_FENCE_RE = re.compile(r"```")
_MD_BOLD_RE = re.compile(r"\*\*")
_MD_HEAD_RE = re.compile(r"(?m)^\s*#\s")
_MD_LIST_RE = re.compile(r"(?m)^\s*-\s")

_QUOTE_RE = re.compile(r'"[^"]{4,}"|\'[^\']{4,}\'')


# ---------------------------------------------------------------------------
# Trajectory helpers
# ---------------------------------------------------------------------------

def _iter_turns(events: list[dict]) -> Iterator[dict]:
    for ev in events:
        if ev.get("event") == "turn":
            yield ev


def _iter_assistant_turns(events: list[dict]) -> Iterator[dict]:
    for ev in _iter_turns(events):
        if ev.get("role") == "assistant":
            yield ev


def _iter_tool_calls(events: list[dict]) -> Iterator[tuple[dict, dict]]:
    """Yield (turn, tool_call) for every tool call in chronological order."""
    for turn in _iter_turns(events):
        for tc in turn.get("tool_calls") or []:
            if isinstance(tc, dict):
                yield turn, tc


def _iter_tool_returns(events: list[dict]) -> Iterator[tuple[dict, dict]]:
    for turn in _iter_turns(events):
        for ret in turn.get("tool_returns") or []:
            if isinstance(ret, dict):
                yield turn, ret


def _tool_call_name(tc: dict) -> str:
    return str(tc.get("name") or "")


def _tool_call_args(tc: dict) -> dict:
    args = tc.get("args")
    if args is None:
        args = tc.get("input")
    return args if isinstance(args, dict) else {}


def _final_assistant_text(events: list[dict]) -> str:
    last = ""
    for turn in _iter_assistant_turns(events):
        out = turn.get("model_output")
        if isinstance(out, str):
            last = out
    return last


def _first_assistant_text_idx(events: list[dict]) -> int | None:
    for turn in _iter_assistant_turns(events):
        out = turn.get("model_output")
        if isinstance(out, str) and out.strip():
            return int(turn.get("idx", 0))
    return None


# Heuristic for read-style tool calls. Tracks Claude Code's `Read` plus
# common synonyms produced by other harnesses (read_file, file_read, etc.).
_READ_TOOL_NAMES = {"Read", "read", "read_file", "file_read", "view", "cat"}


def _is_read_call(tc: dict) -> bool:
    name = _tool_call_name(tc)
    return name in _READ_TOOL_NAMES or name.lower().startswith("read")


def _read_call_path(tc: dict) -> str | None:
    args = _tool_call_args(tc)
    for key in ("file_path", "path", "filename", "filepath", "file"):
        v = args.get(key)
        if isinstance(v, str):
            return v
    return None


def _dotted_get(obj: Any, path: str) -> tuple[bool, Any]:
    """`obj.<a.b.c>` lookup, supports list index via numeric segment."""
    cur: Any = obj
    if not path:
        return True, cur
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError):
                return False, None
        else:
            return False, None
    return True, cur


def _event_idx(ev: dict) -> int:
    try:
        return int(ev.get("idx", 0))
    except (TypeError, ValueError):
        return 0


def _skill_events(events: list[dict]) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for ev in events:
        if ev.get("event") == "skill_invocation":
            name = ev.get("skill") or ev.get("skill_name") or ev.get("name")
            if isinstance(name, str):
                out.append((_event_idx(ev), name))
    for turn, tc in _iter_tool_calls(events):
        if _is_skill_call(tc):
            out.append((_event_idx(turn), _skill_name(tc)))
    return sorted(out, key=lambda x: x[0])


def _mcp_name_matches(name: str, wanted: str) -> bool:
    normalized = wanted.replace("-", "_")
    return name in (wanted, normalized) or wanted in name or normalized in name


def _label_index(events: list[dict], label: str) -> int | None:
    label_l = label.lower()
    if label_l.startswith("read "):
        wanted = label[5:].strip()
        for turn, tc in _iter_tool_calls(events):
            if _is_read_call(tc):
                path = _read_call_path(tc) or ""
                if path == wanted or path.endswith(wanted):
                    return _event_idx(turn)
        return None
    if label_l.startswith("mcp "):
        wanted = label[4:].split("(", 1)[0].strip()
        for turn, tc in _iter_tool_calls(events):
            name = _tool_call_name(tc)
            args = _tool_call_args(tc)
            if (
                name.startswith("mcp__")
                and _mcp_name_matches(name, wanted)
                and ("filename=" not in label or str(args.get("filename") or "") in label)
            ):
                return _event_idx(turn)
        return None
    if label_l == "pytest red":
        return _pytest_event_index(events, success=False)
    if label_l == "pytest green":
        return _pytest_event_index(events, success=True)
    if label_l.startswith("patch "):
        wanted = label[6:].strip()
        for ev in _iter_turns(events):
            diff = ev.get("vault_state_diff") or {}
            paths = [*(diff.get("created") or []), *(diff.get("modified") or []), *(diff.get("deleted") or [])]
            if any(str(p).endswith(wanted) for p in paths):
                return _event_idx(ev)
            for tc in ev.get("tool_calls") or []:
                args = _tool_call_args(tc) if isinstance(tc, dict) else {}
                if any(str(args.get(k, "")).endswith(wanted) for k in ("file_path", "path", "filename")):
                    return _event_idx(ev)
        return None
    return None


def _tool_return_text(ret: dict) -> str:
    parts = []
    for key in ("cmd", "stdout", "stderr", "output", "content", "result"):
        val = ret.get(key)
        if isinstance(val, str):
            parts.append(val)
        elif val is not None:
            parts.append(json.dumps(val, ensure_ascii=False, default=str))
    return "\n".join(parts)


def _pytest_event_index(events: list[dict], *, success: bool, test_id: str | None = None) -> int | None:
    for turn, ret in _iter_tool_returns(events):
        text = _tool_return_text(ret)
        if "pytest" not in text and (test_id is None or test_id not in text):
            continue
        if test_id and test_id not in text:
            continue
        exit_code = ret.get("exit_code")
        if success and exit_code == 0:
            return _event_idx(turn)
        if not success and isinstance(exit_code, int) and exit_code != 0:
            return _event_idx(turn)
        text_l = text.lower()
        if success and (" passed" in text_l or " passed," in text_l):
            return _event_idx(turn)
        if not success and (" failed" in text_l or "error" in text_l):
            return _event_idx(turn)
    return None


def _diff_paths(events: list[dict]) -> tuple[set[str], set[str], set[str]]:
    created: set[str] = set()
    modified: set[str] = set()
    deleted: set[str] = set()
    for ev in _iter_turns(events):
        diff = ev.get("vault_state_diff") or {}
        created.update(str(p) for p in diff.get("created") or [])
        modified.update(str(p) for p in diff.get("modified") or [])
        deleted.update(str(p) for p in diff.get("deleted") or [])
    return created, modified, deleted


_ENTRY_RE = re.compile(r"(?m)^### .*(?:\n(?!### ).*)*")


def _entries(text: str) -> list[str]:
    return [m.group(0).rstrip() for m in _ENTRY_RE.finditer(text)]


def _field_value(entry: str, field: str) -> str | None:
    match = re.search(rf"(?m)^\*\*{re.escape(field)}\*\*:\s*(.*)$", entry)
    return match.group(1).strip() if match else None


def _target_file_pair(workdir: Path | None, fixture_dir: Path | None, p: dict) -> tuple[Path | None, Path | None, str]:
    rel = str(p.get("target_file") or p.get("_target_file") or p.get("path") or "")
    current = _resolve_existing_path(workdir, rel)
    original = _resolve_existing_path(fixture_dir, rel)
    return current, original, rel


def _resolve_existing_path(root: Path | None, rel: str) -> Path | None:
    if root is None or not rel or not root.is_dir():
        return None
    direct = root / rel
    if direct.exists():
        return direct
    basename = Path(rel).name
    matches = sorted(root.rglob(basename))
    return matches[0] if matches else None


def _read_tar_member_bytes(archive: Path, rel: str) -> bytes | None:
    basename = Path(rel).name
    try:
        with tarfile.open(archive, "r:*") as tf:
            members = [m for m in tf.getmembers() if Path(m.name).name == basename and m.isfile()]
            if not members:
                return None
            fh = tf.extractfile(members[0])
            return fh.read() if fh is not None else None
    except (tarfile.TarError, OSError):
        return None


def _read_target_bytes(root: Path | None, rel: str) -> bytes | None:
    if root is None or not rel:
        return None
    if root.is_file():
        return _read_tar_member_bytes(root, rel)
    path = _resolve_existing_path(root, rel)
    return path.read_bytes() if path is not None and path.is_file() else None


def _target_paths(p: dict) -> list[str]:
    raw = p.get("target_paths") or p.get("_target_paths") or []
    if isinstance(raw, str):
        return [raw]
    return [str(x) for x in raw]


def _appended_entries(workdir: Path | None, fixture_dir: Path | None, p: dict) -> tuple[list[str], list[str], str | None]:
    _current, _original, rel = _target_file_pair(workdir, fixture_dir, p)
    current_bytes = _read_target_bytes(workdir, rel)
    if current_bytes is None:
        return [], [], f"target file not found: {rel}"
    before_bytes = _read_target_bytes(fixture_dir, rel)
    current_text = current_bytes.decode("utf-8", errors="replace")
    before_text = before_bytes.decode("utf-8", errors="replace") if before_bytes is not None else ""
    before_entries = _entries(before_text)
    after_entries = _entries(current_text)
    return before_entries, after_entries[len(before_entries):], None


# ---------------------------------------------------------------------------
# Final assistant message — equality, substring, regex, format checks
# ---------------------------------------------------------------------------

def _fa_equals(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    expected = str(p.get("expected", ""))
    if p.get("trim_whitespace"):
        actual = actual.strip()
        expected = expected.strip()
    elif p.get("trim_trailing_newline"):
        actual = actual.rstrip("\n")
        expected = expected.rstrip("\n")
    return actual == expected, {"actual_head": actual[:200], "expected_head": expected[:200]}


def _fa_contains_substring(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    sub = str(p.get("substring", ""))
    return sub in actual, {"substring": sub[:120]}


def _fa_contains_substring_verbatim(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    sub = str(p.get("substring", ""))
    return sub in actual, {"substring": sub[:120], "bytes_exact": True}


def _fa_contains_any(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    terms = list(p.get("terms") or p.get("phrases") or [])
    hits = [t for t in terms if isinstance(t, str) and t in actual]
    return bool(hits), {"hits": hits[:10], "total_terms": len(terms)}


def _fa_contains_at_least_n_of(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    terms = list(p.get("terms") or p.get("phrases") or [])
    n = int(p.get("n", 1))
    hits = [t for t in terms if isinstance(t, str) and t in actual]
    return len(hits) >= n, {"hits": hits[:10], "required_n": n}


def _fa_contains_quoted_span(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    span = str(p.get("span") or p.get("quote") or "")
    quote_chars = p.get("quote_chars") or ['"', "'", "“", "”"]
    # Pair up opens/closes: try every quote-char as both opener and closer.
    for opener in quote_chars:
        for closer in quote_chars:
            if f"{opener}{span}{closer}" in actual:
                return True, {"opener": opener, "closer": closer}
    return False, {"span_head": span[:120], "tried_quotes": quote_chars}


def _fa_does_not_contain(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    forbidden = list(p.get("forbidden") or p.get("substrings") or [])
    if isinstance(p.get("substring"), str):
        forbidden.append(p["substring"])
    hits = [s for s in forbidden if isinstance(s, str) and s in actual]
    return not hits, {"forbidden_hits": hits[:10]}


def _fa_does_not_contain_ci(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events).casefold()
    forbidden = list(p.get("forbidden") or p.get("substrings") or [])
    hits = [s for s in forbidden if isinstance(s, str) and s.casefold() in actual]
    return not hits, {"forbidden_hits": hits[:10]}


def _fa_does_not_match(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    patterns = list(p.get("patterns") or [])
    hits = []
    for pat in patterns:
        if isinstance(pat, str) and re.search(pat, actual):
            hits.append(pat)
    return not hits, {"matched_patterns": hits[:10]}


def _fa_matches_any(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    patterns = list(p.get("patterns") or [])
    hits = [pat for pat in patterns if isinstance(pat, str) and re.search(pat, actual)]
    return bool(hits), {"matched_patterns": hits[:10]}


def _word_count(text: str) -> int:
    # Unicode-aware word splitter — \w covers letters, digits, underscore.
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _fa_word_count(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    n = _word_count(actual)
    if "expected" in p:
        ok = n == int(p["expected"])
        return ok, {"actual": n, "expected": int(p["expected"])}
    lo = p.get("min")
    hi = p.get("max")
    ok = True
    if lo is not None:
        ok = ok and n >= int(lo)
    if hi is not None:
        ok = ok and n <= int(hi)
    return ok, {"actual": n, "min": lo, "max": hi}


def _fa_word_count_min(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    n = _word_count(actual)
    lo = int(p.get("min", 0))
    return n >= lo, {"actual": n, "min": lo}


def _fa_word_count_max(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    n = len(actual.split())
    hi = int(p.get("max", 0))
    return n <= hi, {"actual": n, "max": hi}


def _sentence_count(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    parts = [p for p in re.split(r"[.!?]+", stripped) if p.strip()]
    return len(parts) if parts else 1


def _fa_sentence_count_range(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    n = _sentence_count(actual)
    lo = int(p.get("min", 0))
    hi = int(p.get("max", 10**9))
    return lo <= n <= hi, {"actual": n, "min": lo, "max": hi}


def _fa_no_emoji(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    hits = _EMOJI_RE.findall(actual)
    return not hits, {"emoji_hits": hits[:10], "count": len(hits)}


def _fa_no_markdown(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    triggers: list[str] = []
    if _MD_FENCE_RE.search(actual):
        triggers.append("```")
    if _MD_BOLD_RE.search(actual):
        triggers.append("**")
    if _MD_HEAD_RE.search(actual):
        triggers.append("# ")
    if _MD_LIST_RE.search(actual):
        triggers.append("- ")
    return not triggers, {"markdown_triggers": triggers}


def _fa_no_quotes(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    spans = _QUOTE_RE.findall(actual)
    return not spans, {"quoted_spans": [s[:60] for s in spans[:5]]}


def _no_markdown_fence(events: list[dict], _w, _f, _p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events)
    return not _MD_FENCE_RE.search(actual), {}


def _no_prose_surrounding_json(events: list[dict], _w, _f, _p: dict) -> tuple[bool, dict]:
    actual = _final_assistant_text(events).strip()
    ok = (actual.startswith("{") and actual.endswith("}")) or (
        actual.startswith("[") and actual.endswith("]")
    )
    return ok, {"head": actual[:60], "tail": actual[-60:]}


# ---------------------------------------------------------------------------
# Assistant text (any turn)
# ---------------------------------------------------------------------------

def _assistant_text_mentions_any(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    terms = list(p.get("terms") or p.get("phrases") or [])
    hits: list[str] = []
    for turn in _iter_assistant_turns(events):
        out = turn.get("model_output") or ""
        for t in terms:
            if isinstance(t, str) and t in out and t not in hits:
                hits.append(t)
    return bool(hits), {"hits": hits[:10], "total_terms": len(terms)}


def _assistant_text_nonempty(events: list[dict], _w, _f, _p: dict) -> tuple[bool, dict]:
    for turn in _iter_assistant_turns(events):
        out = turn.get("model_output")
        if isinstance(out, str) and out.strip():
            return True, {"first_idx": int(turn.get("idx", 0))}
    return False, {"reason": "no assistant turn with non-empty model_output"}


# ---------------------------------------------------------------------------
# Turn/tool-call counts
# ---------------------------------------------------------------------------

def _max_turn_count(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    total = sum(1 for _ in _iter_turns(events))
    cap = int(p.get("max", 0))
    return total <= cap, {"actual_turns": total, "max": cap}


def _tool_call_count(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = p.get("tool") or p.get("name")
    expected = int(p.get("expected", 0))
    n = sum(
        1 for _, tc in _iter_tool_calls(events)
        if name is None or _tool_call_name(tc) == name
    )
    return n == expected, {"tool": name, "actual": n, "expected": expected}


def _tool_call_count_min(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = p.get("tool") or p.get("name")
    lo = int(p.get("min", p.get("expected", 0)))
    n = sum(
        1 for _, tc in _iter_tool_calls(events)
        if name is None or _tool_call_name(tc) == name
    )
    return n >= lo, {"tool": name, "actual": n, "min": lo}


def _tool_call_count_max(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = p.get("tool") or p.get("name")
    hi = int(p.get("max", p.get("expected", 0)))
    n = sum(
        1 for _, tc in _iter_tool_calls(events)
        if name is None or _tool_call_name(tc) == name
    )
    return n <= hi, {"tool": name, "actual": n, "max": hi}


def _tool_call_count_total(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    expected = int(p.get("expected", 0))
    n = sum(1 for _turn, _tc in _iter_tool_calls(events))
    return n == expected, {"actual": n, "expected": expected}


def _tool_call_order(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    sequence = list(p.get("order") or p.get("sequence") or [])
    observed = [_tool_call_name(tc) for _, tc in _iter_tool_calls(events)]
    # Subsequence match — every name in `sequence` appears in the observed
    # stream in order, with any other names allowed in between.
    i = 0
    for name in observed:
        if i < len(sequence) and name == sequence[i]:
            i += 1
    return i == len(sequence), {"required": sequence, "observed": observed[:30]}


def _tool_call_name_does_not_match(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    patterns = list(p.get("patterns") or [])
    one = p.get("forbidden_pattern")
    if isinstance(one, str):
        patterns.append(one)
    hits: list[str] = []
    for _, tc in _iter_tool_calls(events):
        name = _tool_call_name(tc)
        for pat in patterns:
            if isinstance(pat, str) and re.search(pat, name):
                hits.append(name)
                break
    return not hits, {"matched_names": hits[:10]}


# ---------------------------------------------------------------------------
# Tool args
# ---------------------------------------------------------------------------

def _first_call_for(events: list[dict], name: str) -> dict | None:
    for _, tc in _iter_tool_calls(events):
        if _tool_call_name(tc) == name:
            return tc
    return None


def _tool_arg_equal(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    arg = str(p.get("arg") or p.get("arg_path") or "")
    expected = p.get("expected")
    tc = _first_call_for(events, name)
    if tc is None:
        return False, {"reason": "no tool call", "tool": name}
    found, actual = _dotted_get(_tool_call_args(tc), arg)
    if not found:
        return False, {"reason": "arg missing", "tool": name, "arg": arg}
    return actual == expected, {"tool": name, "arg": arg, "actual": actual, "expected": expected}


def _tool_args_equal(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    expected = p.get("expected") or {}
    tc = _first_call_for(events, name)
    if tc is None:
        return False, {"reason": "no tool call", "tool": name}
    actual = _tool_call_args(tc)
    return actual == expected, {"tool": name, "actual": actual, "expected": expected}


def _tool_args_equal_across_all_calls(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    expected = p.get("expected") or {}
    calls = [_tool_call_args(tc) for _, tc in _iter_tool_calls(events) if _tool_call_name(tc) == name]
    mismatches = [args for args in calls if args != expected]
    ok = bool(calls) and not mismatches
    return ok, {"tool": name, "calls": len(calls), "mismatches": mismatches[:5], "expected": expected}


def _tool_args_match_schema(
    events: list[dict],
    _w: Path | None,
    fixture_dir: Path | None,
    p: dict,
) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    schema = p.get("schema")
    if schema is None:
        # Schema may live in scorer-level `tool_schema_path` on the fixture.
        schema_path = p.get("_tool_schema_path") or p.get("tool_schema_path")
        if schema_path and fixture_dir is not None:
            try:
                data = json.loads((fixture_dir / schema_path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                return False, {"reason": "schema load failed", "error": str(exc)}
            # The schema file is a `{tools: [{name, parameters}], ...}` dict.
            if isinstance(data, dict):
                tools = data.get("tools") or []
                for entry in tools:
                    if isinstance(entry, dict) and entry.get("name") == name:
                        schema = entry.get("parameters") or entry.get("schema")
                        break
    if not isinstance(schema, dict):
        # No schema available — non-fatal but mark as inconclusive.
        return True, {"reason": "no schema available; skipped", "tool": name}

    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        return True, {"reason": "jsonschema not installed; skipped", "tool": name}

    tc = _first_call_for(events, name)
    if tc is None:
        return False, {"reason": "no tool call", "tool": name}
    try:
        jsonschema.validate(_tool_call_args(tc), schema)
    except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
        return False, {"tool": name, "error": exc.message}
    return True, {"tool": name}


def _tool_arg_array_set_equal(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    arg = str(p.get("arg") or p.get("arg_path") or "")
    expected = list(p.get("expected") or [])
    tc = _first_call_for(events, name)
    if tc is None:
        return False, {"reason": "no tool call", "tool": name}
    found, actual = _dotted_get(_tool_call_args(tc), arg)
    if not found or not isinstance(actual, list):
        return False, {"reason": "arg missing or not list", "tool": name, "arg": arg}

    def _key(item: Any) -> str:
        return json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)

    actual_set = sorted(_key(x) for x in actual)
    expected_set = sorted(_key(x) for x in expected)
    return actual_set == expected_set, {
        "tool": name,
        "arg": arg,
        "actual_count": len(actual),
        "expected_count": len(expected),
    }


def _tool_arg_in_set(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    arg = str(p.get("arg") or p.get("arg_path") or "")
    allowed = list(p.get("allowed") or [])
    tc = _first_call_for(events, name)
    if tc is None:
        return False, {"reason": "no tool call", "tool": name}
    found, actual = _dotted_get(_tool_call_args(tc), arg)
    if not found:
        return False, {"reason": "arg missing", "tool": name, "arg": arg}
    return actual in allowed, {"tool": name, "arg": arg, "actual": actual, "allowed": allowed}


def _tool_arg_distinct_set(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    arg = str(p.get("arg") or p.get("arg_path") or "")
    expected_set = set(p.get("expected_set") or p.get("expected") or [])
    actual_values: list[Any] = []
    missing_arg = 0
    for _, tc in _iter_tool_calls(events):
        if _tool_call_name(tc) != name:
            continue
        found, actual = _dotted_get(_tool_call_args(tc), arg)
        if found:
            actual_values.append(actual)
        else:
            missing_arg += 1
    actual_set = set(actual_values)
    ok = missing_arg == 0 and actual_set == expected_set and len(actual_values) == len(actual_set)
    return ok, {
        "tool": name,
        "arg": arg,
        "actual": sorted(actual_set, key=str),
        "expected": sorted(expected_set, key=str),
        "missing_arg": missing_arg,
    }


def _tool_arg_nonempty(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    arg = str(p.get("arg") or p.get("arg_path") or "")
    tc = _first_call_for(events, name)
    if tc is None:
        return False, {"reason": "no tool call", "tool": name}
    found, actual = _dotted_get(_tool_call_args(tc), arg)
    if not found:
        return False, {"reason": "arg missing", "tool": name, "arg": arg}
    ok = bool(actual.strip()) if isinstance(actual, str) else actual not in (None, [], {})
    return ok, {"tool": name, "arg": arg, "actual_type": type(actual).__name__}


def _tool_arg_contains_any(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    arg = str(p.get("arg") or p.get("arg_path") or "")
    terms = list(p.get("terms") or p.get("phrases") or [])
    tc = _first_call_for(events, name)
    if tc is None:
        return False, {"reason": "no tool call", "tool": name}
    found, actual = _dotted_get(_tool_call_args(tc), arg)
    if not found:
        return False, {"reason": "arg missing", "tool": name, "arg": arg}
    if not isinstance(actual, str):
        return False, {"reason": "arg is not a string", "tool": name, "arg": arg, "actual_type": type(actual).__name__}
    hits = [t for t in terms if isinstance(t, str) and t in actual]
    return bool(hits), {"tool": name, "arg": arg, "hits": hits[:10], "total_terms": len(terms)}


_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "str": (str,),
    "number": (int, float),
    "integer": (int,),
    "int": (int,),
    "float": (float,),
    "boolean": (bool,),
    "bool": (bool,),
    "array": (list,),
    "list": (list,),
    "object": (dict,),
    "dict": (dict,),
    "null": (type(None),),
    "none": (type(None),),
}


def _tool_arg_type(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    arg = str(p.get("arg") or p.get("arg_path") or "")
    expected_type = str(p.get("expected_type") or "").lower()
    forbid_string = bool(p.get("forbid_string"))
    tc = _first_call_for(events, name)
    if tc is None:
        return False, {"reason": "no tool call", "tool": name}
    found, actual = _dotted_get(_tool_call_args(tc), arg)
    if not found:
        return False, {"reason": "arg missing", "tool": name, "arg": arg}
    types = _TYPE_MAP.get(expected_type)
    if types is None:
        return False, {"reason": f"unknown type {expected_type!r}"}
    # Bool is a subclass of int in Python — exclude that conflation for "number".
    if expected_type in {"number", "integer", "int", "float"} and isinstance(actual, bool):
        return False, {"reason": "got bool", "tool": name, "arg": arg, "actual": actual}
    ok = isinstance(actual, types)
    if forbid_string and isinstance(actual, str):
        ok = False
    return ok, {"tool": name, "arg": arg, "actual_type": type(actual).__name__, "expected_type": expected_type}


def _tool_arg_from_prior_return(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    name = str(p.get("tool") or p.get("tool_name") or "")
    arg = str(p.get("arg") or p.get("arg_path") or "")
    source_tool = str(p.get("source_tool") or "")
    source_field = str(p.get("source_field") or p.get("source_path") or "")

    # 1) Find the target tool_call.
    target_tc: dict | None = None
    target_turn_idx = -1
    for turn, tc in _iter_tool_calls(events):
        if _tool_call_name(tc) == name:
            target_tc = tc
            target_turn_idx = int(turn.get("idx", 0))
            break
    if target_tc is None:
        return False, {"reason": "no target tool call", "tool": name}

    found, actual_val = _dotted_get(_tool_call_args(target_tc), arg)
    if not found:
        return False, {"reason": "arg missing", "tool": name, "arg": arg}

    # 2) Scan returns STRICTLY before the target turn for matching source_tool.
    candidates: list[Any] = []
    target_call_id = target_tc.get("id") or target_tc.get("call_id")
    # Build a map of source-tool call ids whose name == source_tool.
    source_ids: set[str] = set()
    for turn, tc in _iter_tool_calls(events):
        if int(turn.get("idx", 0)) >= target_turn_idx:
            continue
        if _tool_call_name(tc) == source_tool:
            cid = tc.get("id") or tc.get("call_id")
            if cid:
                source_ids.add(str(cid))
    for turn, ret in _iter_tool_returns(events):
        if int(turn.get("idx", 0)) >= target_turn_idx:
            continue
        rid = ret.get("tool_use_id") or ret.get("tool_call_id") or ret.get("id")
        if source_ids and (rid is None or str(rid) not in source_ids):
            continue
        # The returned content may be JSON-encoded — try to parse.
        content = ret.get("content") if isinstance(ret.get("content"), (dict, list)) else None
        if content is None:
            raw = ret.get("content") or ret.get("output") or ret.get("result")
            if isinstance(raw, str):
                try:
                    content = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    content = {"_raw": raw}
            else:
                content = ret
        ok, val = _dotted_get(content, source_field)
        if ok:
            candidates.append(val)
        # Also try the bare return dict (some adapters put fields at top level).
        ok2, val2 = _dotted_get(ret, source_field)
        if ok2:
            candidates.append(val2)

    match = actual_val in candidates
    return match, {
        "tool": name,
        "arg": arg,
        "actual": actual_val,
        "source_tool": source_tool,
        "candidates": candidates[:5],
        "target_call_id": target_call_id,
    }


# ---------------------------------------------------------------------------
# Files read
# ---------------------------------------------------------------------------

def _first_file_read(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    allowed = list(p.get("expected_oneof") or p.get("allowed_paths") or [])
    for _, tc in _iter_tool_calls(events):
        if not _is_read_call(tc):
            continue
        path = _read_call_path(tc)
        ok = any(path == a or (isinstance(path, str) and path.endswith(a)) for a in allowed) if path else False
        return ok, {"first_read_path": path, "allowed": allowed}
    return False, {"reason": "no read tool call", "allowed": allowed}


def _file_read_before_first_assistant_text(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    allowed = list(p.get("expected_oneof") or p.get("allowed_paths") or [])
    cutoff = _first_assistant_text_idx(events)
    # If the agent never emits assistant text, the assertion vacuously fails.
    if cutoff is None:
        return False, {"reason": "no assistant text turn"}
    seen: list[str] = []
    for turn, tc in _iter_tool_calls(events):
        if int(turn.get("idx", 0)) >= cutoff:
            break
        if not _is_read_call(tc):
            continue
        path = _read_call_path(tc)
        if path:
            seen.append(path)
        if path and any(path == a or path.endswith(a) for a in allowed):
            return True, {"matched_path": path, "before_idx": cutoff}
    return False, {"reads_before_text": seen[:10], "allowed": allowed, "cutoff_idx": cutoff}


# ---------------------------------------------------------------------------
# Skills / MCP
# ---------------------------------------------------------------------------

def _is_skill_call(tc: dict) -> bool:
    return _tool_call_name(tc) == "Skill"


def _skill_name(tc: dict) -> str:
    args = _tool_call_args(tc)
    v = args.get("skill") or args.get("name")
    return v if isinstance(v, str) else ""


def _skill_invocation_count(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    wanted = str(p.get("skill") or p.get("skill_name") or "")
    n = sum(1 for _, tc in _iter_tool_calls(events) if _is_skill_call(tc) and _skill_name(tc) == wanted)
    if "expected" in p:
        ok = n == int(p["expected"])
        return ok, {"skill": wanted, "actual": n, "expected": int(p["expected"])}
    lo = int(p.get("min", 0))
    return n >= lo, {"skill": wanted, "actual": n, "min": lo}


def _skill_invocation_count_total(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    n = sum(1 for _, tc in _iter_tool_calls(events) if _is_skill_call(tc))
    expected = int(p.get("expected", 0))
    return n == expected, {"actual": n, "expected": expected}


def _first_skill_invocation(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    allowed = p.get("allowed") or p.get("expected_oneof") or []
    if isinstance(allowed, str):
        allowed = [allowed]
    if "expected" in p and p["expected"] not in allowed:
        allowed = [*list(allowed), str(p["expected"])]
    for _, tc in _iter_tool_calls(events):
        if _is_skill_call(tc):
            sk = _skill_name(tc)
            return sk in allowed, {"first_skill": sk, "allowed": list(allowed)}
    return False, {"reason": "no skill invocation", "allowed": list(allowed)}


def _mcp_call_count_total(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    n = sum(
        1 for _, tc in _iter_tool_calls(events)
        if _tool_call_name(tc).startswith("mcp__")
    )
    expected = int(p.get("expected", 0))
    return n == expected, {"actual": n, "expected": expected}


# ---------------------------------------------------------------------------
# Replay JSON compare
# ---------------------------------------------------------------------------

def _replay_then_compare_json(
    events: list[dict],
    workdir: Path | None,
    fixture_dir: Path | None,
    p: dict,
) -> tuple[bool, dict]:
    """Parse the last assistant message as JSON and compare to expected.

    Two YAML shapes are supported:
      - {expected_path: <fixture-relative path>}: load JSON from disk.
      - {target: <relative path>, expected_after_double_apply: <dict>}: the
        idempotency variant. We reconstruct the file state from the trajectory's
        write tool calls applied twice and compare to the expected dict.
    """
    # Variant A: fixture-file comparison.
    expected_path = p.get("expected_path")
    if expected_path and fixture_dir is not None:
        actual_text = _final_assistant_text(events).strip()
        try:
            actual_obj = json.loads(actual_text)
        except json.JSONDecodeError as exc:
            return False, {"reason": "final message is not JSON", "error": str(exc)}
        try:
            expected_obj = json.loads((fixture_dir / expected_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return False, {"reason": "expected file load failed", "error": str(exc)}
        return actual_obj == expected_obj, {"actual_head": actual_text[:120]}

    # Variant B: idempotency-style double-apply check.
    target = p.get("target")
    expected_after = p.get("expected_after_double_apply")
    if target and expected_after is not None:
        # Walk write-style tool calls and reconstruct the JSON file state.
        # We accept Write/Edit/edit_file style payloads. Apply once, then
        # apply again — output must equal `expected_after`.
        def _apply(turns: list[dict]) -> dict | None:
            state: dict | None = None
            for _, tc in turns:
                args = _tool_call_args(tc)
                path = args.get("file_path") or args.get("path")
                if path != target:
                    continue
                content = args.get("content") or args.get("text") or args.get("new_content")
                if isinstance(content, str):
                    with contextlib.suppress(json.JSONDecodeError):
                        state = json.loads(content)
            return state

        write_calls = list(_iter_tool_calls(events))
        after_first = _apply(write_calls)
        after_second = _apply(write_calls)  # same trajectory replayed twice
        ok = after_first == expected_after and after_second == expected_after
        return ok, {"after_first": after_first, "after_second": after_second, "expected": expected_after}

    return False, {"reason": "replay_then_compare_json missing expected_path or target"}


def _load_final_json(events: list[dict]) -> tuple[Any, str | None]:
    text = _final_assistant_text(events).strip()
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def _top_level_key_order(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    obj, err = _load_final_json(events)
    if err:
        return False, {"error": f"final assistant message is not valid JSON: {err}"}
    if not isinstance(obj, dict):
        return False, {"error": "final assistant JSON is not an object"}
    actual = list(obj.keys())
    expected = list(p.get("expected") or [])
    return actual == expected, {"actual": actual, "expected": expected}


def _field_word_count(events: list[dict], _w, _f, p: dict) -> tuple[bool, dict]:
    obj, err = _load_final_json(events)
    if err:
        return False, {"error": f"final assistant message is not valid JSON: {err}"}
    if not isinstance(obj, dict):
        return False, {"error": "final assistant JSON is not an object"}
    field = str(p.get("field") or "")
    value = obj.get(field)
    if not isinstance(value, str):
        return False, {"field": field, "error": "field is not a string"}
    tokenizer = p.get("tokenizer", "word")
    n = len(value.split()) if tokenizer == "whitespace" else _word_count(value)
    expected = int(p.get("expected", 0))
    return n == expected, {"field": field, "actual": n, "expected": expected, "tokenizer": tokenizer}


# ---------------------------------------------------------------------------
# Workdir file-state assertions (post-run live workdir; replay-unfriendly).
# Track B's L0_009 / L0_010 batch needs these to assert atomic-rename
# outcomes and UTF-8 / line-ending invariants without writing per-task code.
# ---------------------------------------------------------------------------


def _resolve_workdir_path(workdir: Path | None, rel: str) -> Path | None:
    if workdir is None:
        return None
    return workdir / rel


def _workdir_file_exists(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    ok = path.is_file()
    return ok, {"path": str(path.name), "exists": ok}


def _workdir_file_absent(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    ok = not path.exists()
    return ok, {"path": str(path.name), "absent": ok}


def _workdir_file_content_equals(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    if not path.is_file():
        return False, {"path": p.get("path"), "error": "file not found"}
    expected = p.get("content", "")
    try:
        actual = path.read_text(encoding=p.get("encoding", "utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return False, {"path": p.get("path"), "error": f"read failed: {exc}"}
    return actual == expected, {
        "path": p.get("path"),
        "match": actual == expected,
        "len_actual": len(actual),
        "len_expected": len(expected),
    }


def _workdir_file_does_not_contain(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    if not path.is_file():
        return False, {"path": p.get("path"), "error": "file not found"}
    forbidden = p.get("forbidden") or p.get("forbidden_substrings") or []
    if isinstance(forbidden, str):
        forbidden = [forbidden]
    try:
        actual = path.read_text(encoding=p.get("encoding", "utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return False, {"path": p.get("path"), "error": f"read failed: {exc}"}
    hits = [s for s in forbidden if isinstance(s, str) and s in actual]
    return not hits, {"path": p.get("path"), "hits": hits}


def _workdir_file_bytes_equal(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    if not path.is_file():
        return False, {"path": p.get("path"), "error": "file not found"}
    expected_bytes = p.get("content", "").encode(p.get("encoding", "utf-8"))
    actual_bytes = path.read_bytes()
    return actual_bytes == expected_bytes, {
        "path": p.get("path"),
        "match": actual_bytes == expected_bytes,
    }


def _workdir_file_no_bom(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    if not path.is_file():
        return False, {"path": p.get("path"), "error": "file not found"}
    head = path.read_bytes()[:3]
    has_bom = head == b"\xef\xbb\xbf"
    return not has_bom, {"path": p.get("path"), "has_bom": has_bom}


def _workdir_file_no_crlf(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    if not path.is_file():
        return False, {"path": p.get("path"), "error": "file not found"}
    data = path.read_bytes()
    has_crlf = b"\r\n" in data
    return not has_crlf, {"path": p.get("path"), "has_crlf": has_crlf}


def _workdir_file_preserves_crlf(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    """For L0_012: assert the file STILL has CRLF after the edit."""
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    if not path.is_file():
        return False, {"path": p.get("path"), "error": "file not found"}
    data = path.read_bytes()
    has_crlf = b"\r\n" in data
    return has_crlf, {"path": p.get("path"), "has_crlf": has_crlf}


def _workdir_file_encoding_utf8(events, workdir, _f, p: dict) -> tuple[bool, dict]:
    path = _resolve_workdir_path(workdir, p.get("path", ""))
    if path is None:
        return False, {"error": "workdir not available (replay mode)"}
    if not path.is_file():
        return False, {"path": p.get("path"), "error": "file not found"}
    try:
        path.read_bytes().decode("utf-8")
        return True, {"path": p.get("path"), "valid_utf8": True}
    except UnicodeDecodeError as exc:
        return False, {"path": p.get("path"), "valid_utf8": False, "error": str(exc)}


def _file_unchanged(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    rel = p.get("path", "")
    current_bytes = _read_target_bytes(workdir, rel)
    original_bytes = _read_target_bytes(fixture_dir, rel)
    if current_bytes is None:
        return False, {"path": rel, "error": "workdir file not found"}
    if original_bytes is None:
        return False, {"path": rel, "error": "fixture file not found"}
    ok = current_bytes == original_bytes
    return ok, {"path": rel, "match": ok, "len_current": len(current_bytes), "len_original": len(original_bytes)}


# ---------------------------------------------------------------------------
# Generic trajectory/state assertions used by L1-L4 tasks.
# ---------------------------------------------------------------------------


def _no_skill_invocation_before(events, _w, _f, p: dict) -> tuple[bool, dict]:
    target = str(p.get("target") or "")
    forbidden = set(p.get("forbidden") or [])
    seen: list[str] = []
    for _idx, name in _skill_events(events):
        if name == target:
            return not any(s in forbidden for s in seen), {"target": target, "seen_before": seen}
        seen.append(name)
    return False, {"target": target, "seen_before": seen, "reason": "target skill not invoked"}


def _trajectory_event_present(events, _w, _f, p: dict) -> tuple[bool, dict]:
    event_type = str(p.get("event_type") or "")
    if event_type == "skill_invocation":
        ok = bool(_skill_events(events))
        return ok, {"event_type": event_type, "count": len(_skill_events(events))}
    count = sum(1 for ev in events if ev.get("event") == event_type)
    return count > 0, {"event_type": event_type, "count": count}


def _mcp_call_with_arg(events, _w, _f, p: dict) -> tuple[bool, dict]:
    wanted = str(p.get("mcp") or "")
    arg_name = str(p.get("arg_name") or "")
    expected = p.get("expected_value")
    matches: list[dict] = []
    for _turn, tc in _iter_tool_calls(events):
        name = _tool_call_name(tc)
        if not name.startswith("mcp__") or not _mcp_name_matches(name, wanted):
            continue
        args = _tool_call_args(tc)
        matches.append({"name": name, "arg": args.get(arg_name)})
        if args.get(arg_name) == expected:
            return True, {"matched": matches[-1]}
    return False, {"expected_mcp": wanted, "arg_name": arg_name, "expected_value": expected, "matches": matches[:5]}


def _ordering(events, _w, _f, p: dict) -> tuple[bool, dict]:
    labels = [p.get("before"), p.get("middle"), p.get("after")]
    labels = [str(x) for x in labels if x]
    positions = [_label_index(events, label) for label in labels]
    ok = all(pos is not None for pos in positions) and positions == sorted(positions)
    return ok, {"labels": labels, "positions": positions}


def _no_event_of_type(events, _w, _f, p: dict) -> tuple[bool, dict]:
    event_type = str(p.get("event_type") or "")
    hits = [ev for ev in events if ev.get("event") == event_type]
    return not hits, {"event_type": event_type, "count": len(hits)}


def _assistant_text_before_hub_load_max_chars(events, _w, _f, p: dict) -> tuple[bool, dict]:
    max_chars = int(p.get("max", 0))
    hub_idx: int | None = None
    for turn, tc in _iter_tool_calls(events):
        name = _tool_call_name(tc)
        args = _tool_call_args(tc)
        if name.startswith("mcp__") and str(args.get("filename") or "").endswith("hub.md"):
            hub_idx = _event_idx(turn)
            break
    if hub_idx is None:
        return False, {"reason": "hub load not found"}
    text = "".join(
        str(ev.get("model_output") or "")
        for ev in _iter_assistant_turns(events)
        if _event_idx(ev) < hub_idx
    )
    return len(text) <= max_chars, {"actual_chars": len(text), "max": max_chars, "hub_idx": hub_idx}


def _pytest_failure_recorded(events, _w, _f, p: dict) -> tuple[bool, dict]:
    test_id = p.get("test_id")
    idx = _pytest_event_index(events, success=False, test_id=str(test_id) if test_id else None)
    return idx is not None, {"test_id": test_id, "idx": idx}


def _pytest_success_recorded(events, _w, _f, p: dict) -> tuple[bool, dict]:
    test_id = p.get("test_id")
    idx = _pytest_event_index(events, success=True, test_id=str(test_id) if test_id else None)
    return idx is not None, {"test_id": test_id, "idx": idx}


def _no_writes(events, _w, _f, _p: dict) -> tuple[bool, dict]:
    created, modified, deleted = _diff_paths(events)
    writes = sorted(created | modified | deleted)
    return not writes, {"writes": writes[:20], "total": len(writes)}


def _read_only_session(events, _w, _f, p: dict) -> tuple[bool, dict]:
    return _no_writes(events, _w, _f, p)


def _only_appended(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    _current, _original, rel = _target_file_pair(workdir, fixture_dir, p)
    before = _read_target_bytes(fixture_dir, rel)
    after = _read_target_bytes(workdir, rel)
    if before is None or after is None:
        return False, {"path": rel, "error": "current/original file unavailable"}
    ok = after.startswith(before)
    return ok, {"path": rel, "before_len": len(before), "after_len": len(after)}


def _prior_entries_unchanged(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    return _only_appended(events, workdir, fixture_dir, p)


def _prior_entries_byte_equal(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    return _only_appended(events, workdir, fixture_dir, p)


def _new_entry_count(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    before_entries, appended, err = _appended_entries(workdir, fixture_dir, p)
    expected = int(p.get("expected", 0))
    if err:
        return False, {"error": err}
    return len(appended) == expected, {"actual": len(appended), "expected": expected, "prior": len(before_entries)}


def _appended_entry_count(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    return _new_entry_count(events, workdir, fixture_dir, p)


def _prior_entry_count(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    before_entries, _appended, err = _appended_entries(workdir, fixture_dir, p)
    expected = int(p.get("expected", 0))
    if err:
        return False, {"error": err}
    return len(before_entries) == expected, {"actual": len(before_entries), "expected": expected}


def _total_entry_count(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    _before, appended, err = _appended_entries(workdir, fixture_dir, p)
    _current, _original, rel = _target_file_pair(workdir, fixture_dir, p)
    expected = int(p.get("expected", 0))
    current_bytes = _read_target_bytes(workdir, rel)
    if err or current_bytes is None:
        return False, {"path": rel, "error": err or "target file not found"}
    actual = len(_entries(current_bytes.decode("utf-8", errors="replace")))
    return actual == expected, {"actual": actual, "expected": expected, "appended": len(appended)}


def _distinct_headings(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    _before, appended, err = _appended_entries(workdir, fixture_dir, p)
    if err:
        return False, {"error": err}
    headings = [entry.splitlines()[0] for entry in appended if entry.splitlines()]
    min_count = int(p.get("min", 1))
    return len(set(headings)) >= min_count, {"headings": headings, "distinct": len(set(headings)), "min": min_count}


def _distinct_importance_values(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    _before, appended, err = _appended_entries(workdir, fixture_dir, p)
    if err:
        return False, {"error": err}
    values = [v for entry in appended if (v := _field_value(entry, "importance")) is not None]
    min_count = int(p.get("min", 1))
    return len(set(values)) >= min_count, {"values": values, "distinct": len(set(values)), "min": min_count}


def _not_all_importance_equal_to(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    _before, appended, err = _appended_entries(workdir, fixture_dir, p)
    if err:
        return False, {"error": err}
    expected_bad = str(p.get("value"))
    values = [v for entry in appended if (v := _field_value(entry, "importance")) is not None]
    ok = bool(values) and not all(v == expected_bad for v in values)
    return ok, {"values": values, "forbidden_uniform_value": expected_bad}


def _file_modified(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    targets = _target_paths(p)
    created, modified, _deleted = _diff_paths(events)
    diff_hit = any(t in created or t in modified for t in targets)
    if diff_hit:
        return True, {"targets": targets, "source": "trajectory_diff"}
    for target in targets:
        if workdir is None or fixture_dir is None:
            continue
        cur = _read_target_bytes(workdir, target)
        old = _read_target_bytes(fixture_dir, target)
        if cur is not None and old is not None and cur != old:
            return True, {"targets": targets, "source": "workdir_diff", "modified": target}
    return False, {"targets": targets, "reason": "no target modified"}


def _line_delta_counts(workdir: Path | None, fixture_dir: Path | None, paths: list[str]) -> tuple[int, int, str | None]:
    if workdir is None or fixture_dir is None:
        return 0, 0, "workdir/fixture_dir unavailable"
    added = 0
    deleted = 0
    for rel in paths:
        cur = _read_target_bytes(workdir, rel)
        old = _read_target_bytes(fixture_dir, rel)
        if cur is None or old is None:
            return 0, 0, f"file unavailable: {rel}"
        diff = difflib.ndiff(
            old.decode("utf-8", errors="replace").splitlines(),
            cur.decode("utf-8", errors="replace").splitlines(),
        )
        for line in diff:
            if line.startswith("+ "):
                added += 1
            elif line.startswith("- "):
                deleted += 1
    return added, deleted, None


def _max_added_lines(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    paths = _target_paths(p)
    added, deleted, err = _line_delta_counts(workdir, fixture_dir, paths)
    cap = int(p.get("max", 0))
    if err:
        return False, {"error": err, "paths": paths}
    return added <= cap, {"added": added, "deleted": deleted, "max": cap, "paths": paths}


def _max_deleted_lines(events, workdir, fixture_dir, p: dict) -> tuple[bool, dict]:
    paths = _target_paths(p)
    added, deleted, err = _line_delta_counts(workdir, fixture_dir, paths)
    cap = int(p.get("max", 0))
    if err:
        return False, {"error": err, "paths": paths}
    return deleted <= cap, {"added": added, "deleted": deleted, "max": cap, "paths": paths}


def _no_unrelated_file_changes(events, _w, _f, p: dict) -> tuple[bool, dict]:
    allowed = set(p.get("allowed") or [])
    created, modified, deleted = _diff_paths(events)
    changed = created | modified | deleted
    unrelated = sorted(path for path in changed if path not in allowed)
    return not unrelated, {"changed": sorted(changed), "allowed": sorted(allowed), "unrelated": unrelated}


# ---------------------------------------------------------------------------
# Registry + chain runner
# ---------------------------------------------------------------------------

_ASSERTION_KINDS: dict[str, AssertionFn] = {
    # workdir file-state (live run only; skipped with workdir=None)
    "workdir_file_exists": _workdir_file_exists,
    "workdir_file_absent": _workdir_file_absent,
    "workdir_file_content_equals": _workdir_file_content_equals,
    "workdir_file_does_not_contain": _workdir_file_does_not_contain,
    "workdir_file_bytes_equal": _workdir_file_bytes_equal,
    "workdir_file_no_bom": _workdir_file_no_bom,
    "workdir_file_no_crlf": _workdir_file_no_crlf,
    "workdir_file_preserves_crlf": _workdir_file_preserves_crlf,
    "workdir_file_encoding_utf8": _workdir_file_encoding_utf8,
    # final assistant message
    "final_assistant_message_equals": _fa_equals,
    "final_assistant_message_contains_substring": _fa_contains_substring,
    "final_assistant_message_contains_substring_verbatim": _fa_contains_substring_verbatim,
    "final_assistant_message_contains_any": _fa_contains_any,
    "final_assistant_message_contains_at_least_n_of": _fa_contains_at_least_n_of,
    "final_assistant_message_contains_quoted_span": _fa_contains_quoted_span,
    "final_assistant_message_does_not_contain": _fa_does_not_contain,
    "final_assistant_message_does_not_contain_ci": _fa_does_not_contain_ci,
    "final_assistant_message_does_not_match": _fa_does_not_match,
    "final_assistant_message_matches_any": _fa_matches_any,
    "final_assistant_message_word_count": _fa_word_count,
    "final_assistant_message_word_count_min": _fa_word_count_min,
    "final_assistant_message_word_count_max": _fa_word_count_max,
    "final_assistant_message_sentence_count_range": _fa_sentence_count_range,
    "final_assistant_message_no_emoji": _fa_no_emoji,
    "final_assistant_message_no_markdown": _fa_no_markdown,
    "final_assistant_message_no_quotes": _fa_no_quotes,
    "no_markdown_fence": _no_markdown_fence,
    "no_prose_surrounding_json": _no_prose_surrounding_json,
    # assistant text (any turn)
    "assistant_text_mentions_any": _assistant_text_mentions_any,
    "assistant_text_nonempty": _assistant_text_nonempty,
    # turn / tool-call counts
    "max_turn_count": _max_turn_count,
    "tool_call_count": _tool_call_count,
    "tool_call_count_min": _tool_call_count_min,
    "tool_call_count_max": _tool_call_count_max,
    "tool_call_count_total": _tool_call_count_total,
    "tool_call_order": _tool_call_order,
    "tool_call_name_does_not_match": _tool_call_name_does_not_match,
    # tool args
    "tool_arg_equal": _tool_arg_equal,
    "tool_args_equal": _tool_args_equal,
    "tool_args_equal_across_all_calls": _tool_args_equal_across_all_calls,
    "tool_args_match_schema": _tool_args_match_schema,
    "tool_arg_array_set_equal": _tool_arg_array_set_equal,
    "tool_arg_in_set": _tool_arg_in_set,
    "tool_arg_distinct_set": _tool_arg_distinct_set,
    "tool_arg_nonempty": _tool_arg_nonempty,
    "tool_arg_contains_any": _tool_arg_contains_any,
    "tool_arg_type": _tool_arg_type,
    "tool_arg_from_prior_return": _tool_arg_from_prior_return,
    # final JSON structure
    "top_level_key_order": _top_level_key_order,
    "field_word_count": _field_word_count,
    # files read
    "first_file_read": _first_file_read,
    "file_read_before_first_assistant_text": _file_read_before_first_assistant_text,
    # skills / MCP
    "skill_invocation_count": _skill_invocation_count,
    "skill_invocation_count_total": _skill_invocation_count_total,
    "first_skill_invocation": _first_skill_invocation,
    "mcp_call_count_total": _mcp_call_count_total,
    # replay JSON
    "replay_then_compare_json": _replay_then_compare_json,
    "file_unchanged": _file_unchanged,
    # generic trajectory assertions
    "no_skill_invocation_before": _no_skill_invocation_before,
    "trajectory_event_present": _trajectory_event_present,
    "mcp_call_with_arg": _mcp_call_with_arg,
    "ordering": _ordering,
    "no_event_of_type": _no_event_of_type,
    "assistant_text_before_hub_load_max_chars": _assistant_text_before_hub_load_max_chars,
    "pytest_failure_recorded": _pytest_failure_recorded,
    "pytest_success_recorded": _pytest_success_recorded,
    # state-diff / memory assertions
    "no_writes": _no_writes,
    "read_only_session": _read_only_session,
    "only_appended": _only_appended,
    "prior_entries_unchanged": _prior_entries_unchanged,
    "prior_entries_byte_equal": _prior_entries_byte_equal,
    "new_entry_count": _new_entry_count,
    "appended_entry_count": _appended_entry_count,
    "prior_entry_count": _prior_entry_count,
    "total_entry_count": _total_entry_count,
    "distinct_headings": _distinct_headings,
    "distinct_importance_values": _distinct_importance_values,
    "not_all_importance_equal_to": _not_all_importance_equal_to,
    "file_modified": _file_modified,
    "max_added_lines": _max_added_lines,
    "max_deleted_lines": _max_deleted_lines,
    "no_unrelated_file_changes": _no_unrelated_file_changes,
}


def run_assertion_chain(
    scorer_name: str,
    events: list[dict],
    workdir: Path | None,
    fixture_dir: Path | None,
    assertions: list[dict],
    *,
    extra_context: dict | None = None,
) -> ScorerVerdict:
    """Walk a list of assertion dicts; produce one ScorerVerdict per scorer.

    `extra_context` keys are passed through into each assertion's `params`
    dict prefixed with `_` (e.g. `tool_schema_path` -> `_tool_schema_path`).
    """
    results: list[dict] = []
    passed = 0
    for raw in assertions or []:
        if not isinstance(raw, dict):
            results.append({"kind": "<invalid>", "ok": False, "detail": {"error": "not a mapping"}})
            continue
        kind = raw.get("kind")
        params = {k: v for k, v in raw.items() if k != "kind"}
        if extra_context:
            for ek, ev in extra_context.items():
                params.setdefault(f"_{ek}", ev)
        fn = _ASSERTION_KINDS.get(kind) if isinstance(kind, str) else None
        if fn is None:
            results.append({"kind": kind, "ok": False, "detail": {"error": "unknown assertion kind"}})
            continue
        try:
            ok, detail = fn(events, workdir, fixture_dir, params)
        except Exception as exc:  # pragma: no cover - defensive
            ok, detail = False, {"error": f"{type(exc).__name__}: {exc}"}
        results.append({"kind": kind, "ok": bool(ok), "detail": detail})
        if ok:
            passed += 1

    total = len(results)
    score = (passed / total) if total else 1.0
    overall_ok = total > 0 and passed == total
    return score_to_verdict(
        scorer_name,
        ScorerKind.deterministic,
        overall_ok,
        score,
        {"assertions": results, "scorer_name": scorer_name, "passed": passed, "total": total},
    )


def load_events(trajectory_path: Path | None) -> list[dict]:
    """Read trajectory JSONL into a flat list of event dicts. Empty on None."""
    if trajectory_path is None:
        return []
    out: list[dict] = []
    with Path(trajectory_path).open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


__all__ = [
    "_ASSERTION_KINDS",
    "AssertionFn",
    "load_events",
    "run_assertion_chain",
]
