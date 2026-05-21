"""memory_check scorer (L1 memory layer).

Backend-agnostic check for L1 "memory operations" tasks. The scorer is a
single dispatcher keyed by `variant`, each variant implementing one of the
five canonical L1 patterns:

  - `write_schema`         — fact written to memory/facts/<id>.json has the
                             canonical key set.
  - `hierarchical_retrieval` — agent's top-K result list achieves at least
                             `precision_threshold` against ground truth.
  - `consolidation`        — agent's deduplicated set is small enough and
                             every consolidated entry retains provenance
                             pointers back to the seed facts.
  - `contradiction_detection` — agent's contradiction-pair set matches the
                             ground-truth pair set (order-independent).
  - `temporal_validity`    — agent's "valid at target_date" set matches the
                             ground-truth filtered set.

Re-runnability (LSN-007): every variant exposes a `replay` path that
reconstructs the agent's output file from the LAST `Write`/`Edit`/etc.
tool_call in the trajectory. Variants that genuinely cannot be replayed
return `replay_unsupported` rather than a false-negative score.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import replay_unsupported, score_to_verdict

_NAME = "memory_check"
_KIND = ScorerKind.deterministic

_WRITE_TOOLS = {
    "Write",
    "Edit",
    "MultiEdit",
    "str_replace_editor",
    "str_replace_based_edit_tool",
    "write_file",
}


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
    args = tc.get("args") or tc.get("input") or {}
    if not isinstance(args, dict):
        return None
    for key in ("content", "file_text", "new_str"):
        v = args.get(key)
        if isinstance(v, str):
            return v
    return None


def _reconstruct_file_from_trajectory(
    trajectory_path: Path,
    target_path: str,
) -> tuple[str | None, bool]:
    last_content: str | None = None
    saw_any_write = False
    base = target_path.rsplit("/", 1)[-1]

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
            if (
                path == target_path
                or path.endswith("/" + target_path)
                or path.rsplit("/", 1)[-1] == base
            ):
                content = _extract_final_content(tc)
                if content is not None:
                    last_content = content

        for ret in ev.get("tool_returns") or []:
            if not isinstance(ret, dict):
                continue
            p = ret.get("path")
            c = ret.get("content")
            if not isinstance(p, str) or not isinstance(c, str):
                continue
            if (
                p == target_path
                or p.endswith("/" + target_path)
                or p.rsplit("/", 1)[-1] == base
            ):
                last_content = c
                saw_any_write = True

    return last_content, saw_any_write


def _read_json(workdir: Path, rel: str) -> tuple[Any, str | None]:
    p = workdir / rel
    if not p.exists() or not p.is_file():
        return None, f"file not found: {rel}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"{rel} is not valid JSON: {exc}"


def _load_ground_truth(
    workdir: Path | None,
    gt_rel: str,
    task: Task | None,
) -> tuple[Any, str | None]:
    candidates: list[Path] = []
    if workdir is not None:
        candidates.append(workdir / gt_rel)
    p = Path(gt_rel)
    if p.is_absolute():
        candidates.append(p)
    try:
        import ab_datasets

        ds_root = Path(ab_datasets.__file__).resolve().parent.parent
        candidates.append(ds_root / gt_rel)
        if not gt_rel.startswith("fixtures/"):
            candidates.append(ds_root / "fixtures" / gt_rel)
    except Exception:
        pass

    for c in candidates:
        if c.exists() and c.is_file():
            try:
                return json.loads(c.read_text(encoding="utf-8")), None
            except json.JSONDecodeError as exc:
                return None, f"ground-truth not valid JSON ({c}): {exc}"
    return None, f"ground-truth file not found: {gt_rel}"


# ---------------------------------------------------------------------------
# variant helpers
# ---------------------------------------------------------------------------


def _check_write_schema(
    payload: Any,
    *,
    expected_path: str,
    expected_schema_keys: list[str],
) -> tuple[bool, float, dict[str, Any]]:
    if not isinstance(payload, dict):
        return False, 0.0, {
            "variant": "write_schema",
            "error": f"expected JSON object at {expected_path}, got {type(payload).__name__}",
        }
    missing = [k for k in expected_schema_keys if k not in payload]
    extra = [k for k in payload if k not in expected_schema_keys]
    score = (len(expected_schema_keys) - len(missing)) / max(1, len(expected_schema_keys))
    ok = not missing
    return ok, score, {
        "variant": "write_schema",
        "path": expected_path,
        "missing_keys": missing,
        "extra_keys": extra,
        "present_keys": [k for k in expected_schema_keys if k in payload],
    }


def _extract_id_list(payload: Any) -> list[str] | None:
    if isinstance(payload, list):
        out: list[str] = []
        for item in payload:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict) and isinstance(item.get("id"), str):
                out.append(item["id"])
            else:
                return None
        return out
    if isinstance(payload, dict):
        results = payload.get("results")
        if isinstance(results, list):
            return _extract_id_list(results)
    return None


def _check_hierarchical_retrieval(
    payload: Any,
    *,
    ground_truth: Any,
    top_k: int,
    precision_threshold: float,
) -> tuple[bool, float, dict[str, Any]]:
    agent_ids = _extract_id_list(payload)
    if agent_ids is None:
        return False, 0.0, {
            "variant": "hierarchical_retrieval",
            "error": "agent output is not a list of ids",
        }
    truth_ids = _extract_id_list(ground_truth)
    if truth_ids is None:
        return False, 0.0, {
            "variant": "hierarchical_retrieval",
            "error": "ground-truth output is not a list of ids",
        }
    top_agent = agent_ids[:top_k]
    top_truth = set(truth_ids[:top_k])
    hits = sum(1 for x in top_agent if x in top_truth)
    precision = hits / max(1, len(top_agent))
    ok = precision >= precision_threshold and len(top_agent) >= min(top_k, len(top_truth))
    return ok, precision, {
        "variant": "hierarchical_retrieval",
        "agent_top_k": top_agent,
        "truth_top_k": sorted(top_truth),
        "hits": hits,
        "precision": precision,
        "precision_threshold": precision_threshold,
    }


def _check_consolidation(
    payload: Any,
    *,
    seed_facts: int,
    expected_consolidated_max: int,
    dedup_rate_threshold: float,
    provenance_required: bool,
) -> tuple[bool, float, dict[str, Any]]:
    if not isinstance(payload, dict):
        return False, 0.0, {
            "variant": "consolidation",
            "error": f"expected JSON object, got {type(payload).__name__}",
        }
    consolidated = payload.get("consolidated")
    if not isinstance(consolidated, list):
        return False, 0.0, {
            "variant": "consolidation",
            "error": "missing or invalid `consolidated` list",
        }

    n_after = len(consolidated)
    dedup_rate = (seed_facts - n_after) / max(1, seed_facts) if seed_facts else 0.0

    issues: list[str] = []
    if n_after > expected_consolidated_max:
        issues.append(
            f"consolidated count {n_after} exceeds expected max {expected_consolidated_max}"
        )
    if dedup_rate < dedup_rate_threshold:
        issues.append(
            f"dedup_rate {dedup_rate:.3f} below threshold {dedup_rate_threshold}"
        )

    missing_prov: list[Any] = []
    if provenance_required:
        for item in consolidated:
            if not isinstance(item, dict):
                missing_prov.append(item)
                continue
            prov = item.get("provenance") or item.get("sources") or item.get("source_ids")
            if not isinstance(prov, list) or not prov:
                missing_prov.append(item.get("id", item))
        if missing_prov:
            issues.append(f"{len(missing_prov)} consolidated entries missing provenance")

    ok = not issues
    score = 1.0 if ok else max(0.0, 1.0 - 0.34 * len(issues))
    return ok, score, {
        "variant": "consolidation",
        "n_seed": seed_facts,
        "n_after": n_after,
        "dedup_rate": dedup_rate,
        "dedup_rate_threshold": dedup_rate_threshold,
        "missing_provenance_count": len(missing_prov),
        "issues": issues,
    }


def _extract_pair_set(payload: Any) -> set[frozenset[str]] | None:
    if isinstance(payload, dict):
        payload = payload.get("contradictions") or payload.get("pairs") or payload.get("results")
    if not isinstance(payload, list):
        return None
    out: set[frozenset[str]] = set()
    for item in payload:
        if isinstance(item, list) and len(item) == 2 and all(isinstance(x, str) for x in item):
            out.add(frozenset(item))
        elif (
            isinstance(item, dict)
            and isinstance(item.get("a"), str)
            and isinstance(item.get("b"), str)
        ):
            out.add(frozenset([item["a"], item["b"]]))
        else:
            return None
    return out


def _check_contradiction(
    payload: Any,
    *,
    ground_truth: Any,
) -> tuple[bool, float, dict[str, Any]]:
    agent_pairs = _extract_pair_set(payload)
    truth_pairs = _extract_pair_set(ground_truth)
    if agent_pairs is None:
        return False, 0.0, {
            "variant": "contradiction_detection",
            "error": "agent output is not a pair-set",
        }
    if truth_pairs is None:
        return False, 0.0, {
            "variant": "contradiction_detection",
            "error": "ground-truth output is not a pair-set",
        }
    tp = len(agent_pairs & truth_pairs)
    fp = len(agent_pairs - truth_pairs)
    fn = len(truth_pairs - agent_pairs)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)
    ok = agent_pairs == truth_pairs
    return ok, f1, {
        "variant": "contradiction_detection",
        "agent_pairs": sorted(list(p) for p in agent_pairs),
        "truth_pairs": sorted(list(p) for p in truth_pairs),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _extract_id_set(payload: Any) -> set[str] | None:
    ids = _extract_id_list(payload)
    if ids is None:
        if isinstance(payload, dict):
            for key in ("valid_ids", "valid", "facts", "active"):
                inner = payload.get(key)
                ids = _extract_id_list(inner)
                if ids is not None:
                    return set(ids)
        return None
    return set(ids)


def _check_temporal_validity(
    payload: Any,
    *,
    ground_truth: Any,
) -> tuple[bool, float, dict[str, Any]]:
    agent_ids = _extract_id_set(payload)
    truth_ids = _extract_id_set(ground_truth)
    if agent_ids is None:
        return False, 0.0, {
            "variant": "temporal_validity",
            "error": "agent output is not an id list",
        }
    if truth_ids is None:
        return False, 0.0, {
            "variant": "temporal_validity",
            "error": "ground-truth output is not an id list",
        }
    tp = len(agent_ids & truth_ids)
    fp = len(agent_ids - truth_ids)
    fn = len(truth_ids - agent_ids)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-9, precision + recall)
    ok = agent_ids == truth_ids
    return ok, f1, {
        "variant": "temporal_validity",
        "agent_ids": sorted(agent_ids),
        "truth_ids": sorted(truth_ids),
        "extra": sorted(agent_ids - truth_ids),
        "missing": sorted(truth_ids - agent_ids),
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _parse_iso_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def memory_check_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    variant: str | None = None,
    expected_path: str | None = None,
    expected_schema_keys: list[str] | None = None,
    ground_truth_path: str | None = None,
    top_k: int = 5,
    precision_threshold: float = 0.6,
    seed_facts: int | None = None,
    expected_consolidated_max: int | None = None,
    dedup_rate_threshold: float = 0.2,
    provenance_required: bool = True,
    expected_contradictions_path: str | None = None,
    expected_valid_path: str | None = None,
    output_path: str | None = None,
    **_: Any,
) -> ScorerVerdict:
    if variant not in {
        "write_schema",
        "hierarchical_retrieval",
        "consolidation",
        "contradiction_detection",
        "temporal_validity",
    }:
        return score_to_verdict(_NAME, _KIND, False, 0.0, {
            "error": f"unknown or missing `variant`: {variant!r}",
        })

    default_outputs = {
        "write_schema": expected_path,
        "hierarchical_retrieval": "memory/results.json",
        "consolidation": "memory/consolidated.json",
        "contradiction_detection": "memory/contradictions.json",
        "temporal_validity": "memory/valid_at.json",
    }
    out_rel = output_path or default_outputs.get(variant)
    if out_rel is None:
        return score_to_verdict(_NAME, _KIND, False, 0.0, {
            "error": f"variant={variant} requires output_path (or expected_path for write_schema)",
        })

    payload: Any
    if mode == "replay" or workdir is None:
        if trajectory_path is None:
            return replay_unsupported(_NAME, _KIND, "trajectory_path required for replay")
        raw, saw_write = _reconstruct_file_from_trajectory(trajectory_path, out_rel)
        if not saw_write:
            return replay_unsupported(
                _NAME, _KIND,
                f"no write-style tool_calls in trajectory; cannot reconstruct {out_rel!r}",
            )
        if raw is None:
            return replay_unsupported(
                _NAME, _KIND,
                f"final content for {out_rel!r} not reconstructable from trajectory",
            )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {
                "variant": variant,
                "error": f"reconstructed content is not valid JSON: {exc}",
                "mode": "replay",
            })
    else:
        payload, err = _read_json(workdir, out_rel)
        if err is not None:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {
                "variant": variant,
                "error": err,
            })

    if variant == "write_schema":
        if not expected_path or not expected_schema_keys:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {
                "error": "write_schema requires expected_path and expected_schema_keys",
            })
        ok, score, detail = _check_write_schema(
            payload,
            expected_path=expected_path,
            expected_schema_keys=expected_schema_keys,
        )

    elif variant == "hierarchical_retrieval":
        if ground_truth_path is None:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {
                "error": "hierarchical_retrieval requires ground_truth_path",
            })
        truth, terr = _load_ground_truth(workdir, ground_truth_path, task)
        if terr:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {"error": terr})
        ok, score, detail = _check_hierarchical_retrieval(
            payload,
            ground_truth=truth,
            top_k=top_k,
            precision_threshold=precision_threshold,
        )

    elif variant == "consolidation":
        if seed_facts is None or expected_consolidated_max is None:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {
                "error": "consolidation requires seed_facts and expected_consolidated_max",
            })
        ok, score, detail = _check_consolidation(
            payload,
            seed_facts=seed_facts,
            expected_consolidated_max=expected_consolidated_max,
            dedup_rate_threshold=dedup_rate_threshold,
            provenance_required=provenance_required,
        )

    elif variant == "contradiction_detection":
        gt_path = expected_contradictions_path or ground_truth_path
        if gt_path is None:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {
                "error": "contradiction_detection requires expected_contradictions_path",
            })
        truth, terr = _load_ground_truth(workdir, gt_path, task)
        if terr:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {"error": terr})
        ok, score, detail = _check_contradiction(payload, ground_truth=truth)

    else:
        gt_path = expected_valid_path or ground_truth_path
        if gt_path is None:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {
                "error": "temporal_validity requires expected_valid_path",
            })
        truth, terr = _load_ground_truth(workdir, gt_path, task)
        if terr:
            return score_to_verdict(_NAME, _KIND, False, 0.0, {"error": terr})
        ok, score, detail = _check_temporal_validity(payload, ground_truth=truth)

    detail["mode"] = "replay" if mode == "replay" or workdir is None else "run"
    return score_to_verdict(_NAME, _KIND, ok, score, detail)
