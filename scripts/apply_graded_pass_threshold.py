"""Apply graded pass_threshold to multi-axis L0 tasks.

These tasks have ≥4 independent assertion axes (e.g. IFBench-style word
count + sentence count + forbidden + mandatory). Partial credit on
independent axes is a meaningful signal — it rewards weaker models that
satisfy most but not all simultaneous constraints.

Tasks NOT touched: NIAH+sha1 chains and other tasks where the primary
assertion is a single byte-exact answer + decoy guards — partial credit
there would be a false positive (right format, wrong answer).

Run:
    python3 scripts/apply_graded_pass_threshold.py --dry-run
    python3 scripts/apply_graded_pass_threshold.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
L0_DIR = ROOT / "packages" / "ab-datasets" / "ab_datasets" / "L0_foundation"

# (task_id, scorer_name_substring, pass_threshold)
TARGETS = [
    ("L0_401", "ifbench", 0.70),
    ("L0_402", "three_axis", 0.70),
    ("L0_403", "json", 0.75),
    ("L0_404", None, 0.75),  # apply to first deterministic scorer with multi assertions
    ("L0_406", None, 0.75),
    ("L0_011", None, 0.70),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)

    changes = 0
    for tid, scorer_substr, threshold in TARGETS:
        matches = list(L0_DIR.glob(f"{tid}-*.yaml"))
        if not matches:
            print(f"  MISS {tid} — no YAML found")
            continue
        path = matches[0]
        doc = yaml.load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            print(f"  SKIP {tid} — not a mapping")
            continue
        applied_here = False
        for sc in doc.get("scorer_chain") or []:
            if not isinstance(sc, dict):
                continue
            name = sc.get("name", "")
            if scorer_substr and scorer_substr not in name:
                continue
            cfg = sc.get("config") or {}
            asserts = cfg.get("assertions") or []
            if len(asserts) < 3:
                continue
            cur = cfg.get("pass_threshold")
            if cur is not None and float(cur) <= threshold:
                # Already at or below desired threshold — skip.
                continue
            cfg["pass_threshold"] = threshold
            if "config" not in sc:
                sc["config"] = cfg
            print(f"  {tid} / scorer '{name}': pass_threshold = {threshold} ({len(asserts)} assertions)")
            applied_here = True
            changes += 1
            break  # only first matching scorer per task
        if not applied_here:
            print(f"  NO-OP {tid} — no suitable scorer matched")
        elif args.apply:
            with path.open("w", encoding="utf-8") as fh:
                yaml.dump(doc, fh)

    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"\n{mode}: {changes} task scorers tagged for graded threshold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
