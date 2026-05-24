"""Lever A — bulk-tighten all 104 L0 foundation YAMLs.

Mechanical changes only (no new content):

1. Raise pass_thresholds:
   - tool_skill:          0.5  -> 0.8
   - context_efficiency:  0.3/0.4 -> 0.6
   - latency_cost:        0.3/0.4 -> 0.6

2. Halve budgets (with safety floor = target_value * 2):
   - max_tokens: halve, floor max(target_tokens * 2, current // 2)
   - max_ms:     halve, floor max(target_ms     * 2, current // 2)
   - max_tool_calls: halve if > 5, floor at 3

3. Memory pillar activation on environment-probe + faithfulness (L0_5xx / L0_6xx, 25 tasks):
   - correctness weight -= 0.15, memory_specific weight += 0.15

4. Stricter redundant_ratio not in YAML — handled in tool_skill.py separately.

Run:
    uv run python scripts/tighten_l0_lever_a.py --dry-run
    uv run python scripts/tighten_l0_lever_a.py --apply

The script reads YAMLs with ruamel.yaml (round-trip preserves formatting +
comments), edits in place, writes back. Always idempotent — running twice
produces no further diff.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

# --- config ----------------------------------------------------------------

L0_DIR = Path(__file__).resolve().parents[1] / "packages" / "ab-datasets" / "ab_datasets" / "L0_foundation"

# Target pillar thresholds after Lever A.
NEW_PASS_THRESHOLDS = {
    "tool_skill": 0.8,
    "context_efficiency": 0.6,
    "latency_cost": 0.6,
}

# Families that gain memory_specific weight.
MEMORY_FAMILY_PREFIXES = ("L0_5", "L0_6")  # faithfulness + environment-probe
MEMORY_WEIGHT = 0.15  # taken from correctness


def _new_max(current: int | None, target: int | None) -> int | None:
    """Halve `current` but never below `target * 2`."""
    if current is None:
        return None
    halved = current // 2
    if target is None:
        return halved
    floor = int(target) * 2
    return max(halved, floor)


def _new_tool_call_cap(current: int | None) -> int | None:
    if current is None:
        return None
    if current <= 5:
        return current  # already tight
    return max(3, current // 2)


def _tighten_scorer(scorer: dict, family_prefix: str | None = None) -> list[str]:
    """In-place tighten of one scorer block. Returns list of human-readable changes."""
    name = scorer.get("name")
    cfg = scorer.get("config") or {}
    changes: list[str] = []

    new_pt = NEW_PASS_THRESHOLDS.get(name)
    if new_pt is not None:
        cur_pt = cfg.get("pass_threshold")
        if cur_pt is not None and float(cur_pt) < new_pt:
            cfg["pass_threshold"] = new_pt
            changes.append(f"{name}.pass_threshold {cur_pt} -> {new_pt}")

    # Budget caps (max_tokens, max_ms, max_tool_calls).
    if "max_tokens" in cfg:
        old = cfg["max_tokens"]
        new = _new_max(old, cfg.get("target_tokens"))
        if new != old:
            cfg["max_tokens"] = new
            changes.append(f"{name}.max_tokens {old} -> {new}")

    if "max_ms" in cfg:
        old = cfg["max_ms"]
        new = _new_max(old, cfg.get("target_ms"))
        if new != old:
            cfg["max_ms"] = new
            changes.append(f"{name}.max_ms {old} -> {new}")

    if "max_tool_calls" in cfg:
        old = cfg["max_tool_calls"]
        new = _new_tool_call_cap(old)
        if new != old:
            cfg["max_tool_calls"] = new
            changes.append(f"{name}.max_tool_calls {old} -> {new}")

    if cfg and "config" not in scorer:
        scorer["config"] = cfg
    return changes


def _tighten_weights(doc: dict, task_id: str) -> list[str]:
    """If task_id starts with L0_5 / L0_6, shift 0.15 from correctness to memory_specific."""
    changes: list[str] = []
    if not any(task_id.startswith(pref) for pref in MEMORY_FAMILY_PREFIXES):
        return changes

    weights = doc.get("weights")
    if not isinstance(weights, dict):
        return changes

    cur_corr = float(weights.get("correctness", 0))
    cur_mem = float(weights.get("memory_specific", 0))
    if cur_mem >= MEMORY_WEIGHT - 1e-9:
        return changes  # already activated
    if cur_corr < MEMORY_WEIGHT + 0.05:
        # Don't push correctness too low — skip if no room.
        return changes

    weights["correctness"] = round(cur_corr - MEMORY_WEIGHT, 4)
    weights["memory_specific"] = round(cur_mem + MEMORY_WEIGHT, 4)
    changes.append(
        f"weights.correctness {cur_corr} -> {weights['correctness']}, "
        f"memory_specific {cur_mem} -> {weights['memory_specific']}"
    )
    return changes


def tighten_file(path: Path, yaml: YAML, *, apply: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    doc = yaml.load(text)
    if not isinstance(doc, dict):
        return [f"SKIP (not a mapping): {path.name}"]

    task_id = str(doc.get("id") or path.stem.split("-", 1)[0])
    all_changes: list[str] = []

    for scorer in doc.get("scorer_chain") or []:
        if isinstance(scorer, dict):
            all_changes.extend(_tighten_scorer(scorer, family_prefix=task_id))

    all_changes.extend(_tighten_weights(doc, task_id))

    if all_changes and apply:
        with path.open("w", encoding="utf-8") as fh:
            yaml.dump(doc, fh)

    return all_changes


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    ap.add_argument("--files", nargs="*", help="Limit to specific YAML paths")
    args = ap.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096  # avoid line-wrap reformatting on long expected strings
    yaml.indent(mapping=2, sequence=4, offset=2)

    files = (
        [Path(p) for p in args.files]
        if args.files
        else sorted(L0_DIR.glob("L0_*.yaml"))
    )

    if not files:
        print(f"no YAMLs found under {L0_DIR}", file=sys.stderr)
        return 2

    total_changed = 0
    total_change_lines = 0
    for path in files:
        changes = tighten_file(path, yaml, apply=args.apply)
        if changes:
            total_changed += 1
            total_change_lines += len(changes)
            print(f"\n{path.name}")
            for c in changes:
                print(f"  - {c}")

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n{mode}: {total_changed}/{len(files)} files would change, {total_change_lines} edits total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
