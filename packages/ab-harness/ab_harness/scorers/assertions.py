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
import json
import re
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


# ---------------------------------------------------------------------------
# Registry + chain runner
# ---------------------------------------------------------------------------

_ASSERTION_KINDS: dict[str, AssertionFn] = {
    # workdir file-state (live run only; skipped with workdir=None)
    "workdir_file_exists": _workdir_file_exists,
    "workdir_file_absent": _workdir_file_absent,
    "workdir_file_content_equals": _workdir_file_content_equals,
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
    "final_assistant_message_does_not_match": _fa_does_not_match,
    "final_assistant_message_matches_any": _fa_matches_any,
    "final_assistant_message_word_count": _fa_word_count,
    "final_assistant_message_word_count_min": _fa_word_count_min,
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
    "tool_call_order": _tool_call_order,
    "tool_call_name_does_not_match": _tool_call_name_does_not_match,
    # tool args
    "tool_arg_equal": _tool_arg_equal,
    "tool_args_equal": _tool_args_equal,
    "tool_args_match_schema": _tool_args_match_schema,
    "tool_arg_array_set_equal": _tool_arg_array_set_equal,
    "tool_arg_in_set": _tool_arg_in_set,
    "tool_arg_type": _tool_arg_type,
    "tool_arg_from_prior_return": _tool_arg_from_prior_return,
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
