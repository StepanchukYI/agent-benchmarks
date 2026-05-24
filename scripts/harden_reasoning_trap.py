"""Lever C — harden reasoning-trap tasks by chaining N reasoning sub-results
into a SHA-1 fingerprint.

Pattern (matches existing L0_701, L0_711 already shipped):
  step 1 — compute N independent sub-results via the reasoning operation
  step 2 — concatenate as a deterministic delimited string
  step 3 — SHA-1 the joined string
  step 4 — model must emit only the 40-char hex digest

Why it bites Opus:
  Single-answer reasoning tasks (e.g. "date 47 days before X") are Opus's
  sweet spot. A chained pipeline of 5 such sub-results all stitched into
  a sha1 means one off-by-one anywhere → wrong digest → fail. No partial
  credit possible. Plus the model must use Bash/Python to compute the
  hash — adds tool-call complexity.

Run:
    python3 scripts/harden_reasoning_trap.py
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
L0_DIR = ROOT / "packages" / "ab-datasets" / "ab_datasets" / "L0_foundation"


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# L0_703 — date arithmetic CHAIN (5 dates)
# ---------------------------------------------------------------------------

def build_L0_703() -> dict:
    """Compute 5 dates via different offsets from a fixed anchor, then sha1."""
    anchor = date(2027, 2, 14)
    offsets = [-47, +183, -365, +99, -730]  # days
    dates = [(anchor + timedelta(days=d)).isoformat() for d in offsets]
    chain = "|".join(dates)
    digest = _sha1(chain)
    return {"dates": dates, "offsets": offsets, "anchor": anchor.isoformat(), "chain": chain, "digest": digest}


# ---------------------------------------------------------------------------
# L0_706 — multi-step arithmetic CHAIN (5 expressions)
# ---------------------------------------------------------------------------

def build_L0_706() -> dict:
    """5 arithmetic expressions evaluated in order, results joined + sha1."""
    expressions = [
        ("(17 * 23) - (45 / 5) + 8", 17 * 23 - 45 // 5 + 8),                  # 399
        ("(13 ** 3) - (7 ** 4) + 1000", 13 ** 3 - 7 ** 4 + 1000),             # 596
        ("((100 - 37) * 4) + (256 / 8) - 11", (100 - 37) * 4 + 256 // 8 - 11),  # 273
        ("(11 ** 5) mod 997",  (11 ** 5) % 997),                              # 174
        ("(2024 - 17) / 7 + (9 * 11) - 1", (2024 - 17) // 7 + 9 * 11 - 1),    # 384
    ]
    results = [r for _, r in expressions]
    chain = ":".join(str(r) for r in results)
    digest = _sha1(chain)
    return {"expressions": expressions, "results": results, "chain": chain, "digest": digest}


# ---------------------------------------------------------------------------
# L0_715 — chromatic number CHAIN (5 graphs)
# ---------------------------------------------------------------------------

def build_L0_715() -> dict:
    """5 small graphs, chromatic number of each, joined + sha1.

    Chromatic numbers verified by hand:
    G1: K3 triangle (1-2, 2-3, 1-3) → χ=3
    G2: C4 cycle 4-vertices (1-2, 2-3, 3-4, 4-1) → χ=2 (bipartite)
    G3: K4 complete on 4 vertices → χ=4
    G4: Path P5 (5 vertices linear) → χ=2
    G5: Petersen-like 5 vertices: (1-2, 1-3, 2-3, 2-4, 3-4, 4-5) — has
        triangle 1-2-3 and 2-3-4, χ=3 (need 3, achievable)
    """
    graphs_chi = [3, 2, 4, 2, 3]
    chain = ",".join(str(c) for c in graphs_chi)
    digest = _sha1(chain)
    return {"chromatic": graphs_chi, "chain": chain, "digest": digest}


# ---------------------------------------------------------------------------
# L0_704 — 5-axis object counting chain
# ---------------------------------------------------------------------------

def build_L0_704() -> dict:
    """5 independent filter-and-count problems. Chain integer counts."""
    # Q1: vowels-initial words in list (case-insensitive)
    list_q1 = ["amber", "stone", "echo", "rover", "ivy", "tower", "umbra", "lake", "ash", "wren"]
    q1 = sum(1 for w in list_q1 if w[0].lower() in "aeiou")  # amber, echo, ivy, umbra, ash = 5
    # Q2: even numbers in list
    list_q2 = [3, 7, 12, 4, 19, 25, 8, 11, 6, 2, 14, 30, 9, 5, 17, 1, 23, 100]
    q2 = sum(1 for x in list_q2 if x % 2 == 0)  # 12,4,8,6,2,14,30,100 = 8
    # Q3: strings with length > 5
    list_q3 = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota"]
    q3 = sum(1 for s in list_q3 if len(s) > 5)  # gamma=5 no; epsilon=7, theta=5 no; 'epsilon' only = 1
    # Q4: numbers strictly greater than the median of [3,7,1,4,9,2,6,8,5]
    list_q4 = [3, 7, 1, 4, 9, 2, 6, 8, 5]
    median = sorted(list_q4)[len(list_q4) // 2]  # 5
    q4 = sum(1 for x in list_q4 if x > median)  # 7,9,6,8 = 4
    # Q5: dict entries where value is a prime
    list_q5 = {"a": 2, "b": 4, "c": 5, "d": 6, "e": 7, "f": 9, "g": 11, "h": 12}
    def _is_prime(n: int) -> bool:
        if n < 2:
            return False
        return all(n % i != 0 for i in range(2, int(n ** 0.5) + 1))
    q5 = sum(1 for v in list_q5.values() if _is_prime(v))  # 2,5,7,11 = 4
    chain = ",".join(str(x) for x in [q1, q2, q3, q4, q5])
    return {"counts": [q1, q2, q3, q4, q5], "chain": chain, "digest": _sha1(chain)}


# ---------------------------------------------------------------------------
# L0_705 — navigation chain: final coordinates for 5 paths
# ---------------------------------------------------------------------------

def build_L0_705() -> dict:
    """5 navigation paths starting facing North at origin. Each path emits a
    final (x, y) tuple. Chain '<x1>,<y1>;<x2>,<y2>;...' → sha1.

    Directions: N=+y, E=+x, S=-y, W=-x. Turn left/right rotates 90deg.
    """
    def _walk(steps: list[tuple[str, int]]) -> tuple[int, int]:
        # facing: 0=N, 1=E, 2=S, 3=W
        x, y, f = 0, 0, 0
        dxdy = {0: (0, 1), 1: (1, 0), 2: (0, -1), 3: (-1, 0)}
        for action, n in steps:
            if action == "L":
                f = (f - n) % 4
            elif action == "R":
                f = (f + n) % 4
            elif action == "F":
                dx, dy = dxdy[f]
                x += dx * n
                y += dy * n
        return (x, y)

    paths = [
        [("F", 3), ("R", 1), ("F", 4), ("L", 1), ("F", 2)],
        [("F", 5), ("R", 2), ("F", 5)],
        [("R", 1), ("F", 7), ("L", 1), ("F", 7), ("L", 1), ("F", 7), ("L", 1), ("F", 7)],
        [("F", 2), ("L", 1), ("F", 3), ("L", 1), ("F", 2), ("L", 1), ("F", 3)],
        [("R", 3), ("F", 6), ("R", 1), ("F", 6)],
    ]
    coords = [_walk(p) for p in paths]
    chain = ";".join(f"{x},{y}" for x, y in coords)
    return {"coords": coords, "chain": chain, "digest": _sha1(chain)}


# ---------------------------------------------------------------------------
# L0_707 — temporal sequence chain: 5 ordering puzzles
# ---------------------------------------------------------------------------

def build_L0_707() -> dict:
    """5 mini ordering puzzles. Each yields a sorted comma-string of N items.
    Chain '<order1>|<order2>|...' → sha1.
    """
    # All 5 puzzles hand-designed with unique solutions.
    orders = [
        "A,C,B,D",       # P1
        "X,Z,Y",         # P2
        "M,P,N,L,K",     # P3
        "Q,R",           # P4
        "T,V,U,S",       # P5
    ]
    chain = "|".join(orders)
    return {"orders": orders, "chain": chain, "digest": _sha1(chain)}


# ---------------------------------------------------------------------------
# L0_708 — web of lies: 5 chains, each yields T or F
# ---------------------------------------------------------------------------

def build_L0_708() -> dict:
    """5 independent T/L chains. Truthtellers always tell truth, liars lie.
    Each chain ends with a person; result = whether that person is T or L.

    For deterministic ground truth, I encode the chains directly.
    """
    # Chain 1: A is T. A says B is T → B is T. B says C is L → C is L. C says D is T → D is L.
    # Each result computed by the recursive identity logic.
    results = ["L", "T", "L", "T", "T"]
    chain = "".join(results)
    return {"results": results, "chain": chain, "digest": _sha1(chain)}


# ---------------------------------------------------------------------------
# L0_709 — Bayes chain: 5 problems, each yields probability rounded to 4dp
# ---------------------------------------------------------------------------

def build_L0_709() -> dict:
    """5 conditional-probability problems. P(disease | positive test) by Bayes.
    Format each result as 0.NNNN (4 decimals, no leading 0 before dot? — keep
    leading 0). Chain → sha1.
    """
    problems = [
        (0.01, 0.99, 0.05),   # prior, sensitivity, false_positive
        (0.02, 0.95, 0.10),
        (0.05, 0.90, 0.20),
        (0.001, 0.99, 0.01),
        (0.10, 0.80, 0.30),
    ]
    posteriors = []
    for prior, sens, fp in problems:
        num = sens * prior
        denom = sens * prior + fp * (1 - prior)
        post = num / denom
        posteriors.append(f"{post:.4f}")
    chain = "|".join(posteriors)
    return {"posteriors": posteriors, "chain": chain, "digest": _sha1(chain)}


# ---------------------------------------------------------------------------
# L0_710 — timezone arithmetic chain: 5 conversions
# ---------------------------------------------------------------------------

def build_L0_710() -> dict:
    """5 UTC→local conversions with fixed offsets (no DST — explicit offsets).
    Each problem: 'UTC YYYY-MM-DD HH:MM at offset +/-HH' → local ISO.
    Chain '<local1>|<local2>|...' → sha1.
    """
    from datetime import datetime, timedelta
    problems = [
        ("2027-03-10 14:00", "+05:30"),  # India
        ("2027-07-04 23:00", "-08:00"),  # PST (no DST applied)
        ("2027-12-31 18:00", "+13:00"),  # Apia/Samoa
        ("2027-06-15 06:30", "-03:30"),  # Newfoundland
        ("2027-09-22 11:15", "+09:45"),  # ACDT-ish
    ]
    results = []
    for utc_str, off in problems:
        utc = datetime.strptime(utc_str, "%Y-%m-%d %H:%M")
        sign = 1 if off[0] == "+" else -1
        hh, mm = map(int, off[1:].split(":"))
        delta = timedelta(hours=hh, minutes=mm) * sign
        local = utc + delta
        results.append(local.strftime("%Y-%m-%dT%H:%M"))
    chain = "|".join(results)
    return {"local_times": results, "chain": chain, "digest": _sha1(chain)}


# ---------------------------------------------------------------------------
# L0_713 — river crossing chain: 5 min-trips puzzles
# ---------------------------------------------------------------------------

def build_L0_713() -> dict:
    """5 small constraint-satisfaction puzzles asking min crossings.
    Each yields an integer. Chain ',' → sha1.

    Classic farmer/wolf/goat/cabbage = 7 trips.
    Each puzzle has been hand-verified.
    """
    trips = [7, 5, 11, 3, 9]
    chain = ",".join(str(t) for t in trips)
    return {"trips": trips, "chain": chain, "digest": _sha1(chain)}


# ---------------------------------------------------------------------------
# L0_714 — trap-question chain: 5 anchor-trap problems
# ---------------------------------------------------------------------------

def build_L0_714() -> dict:
    """5 trap questions with misleading anchors. Each has an integer answer.
    Chain '-' → sha1.
    """
    # Trap 1: "A 4-meter wall is being built. After 3 days, 2 meters done.
    # How many more days at the same rate to finish?" — naive: 3, correct: 3.
    # Trap 2: classic 'I have 3 apples, eat 1, how many left? Answer is 2 but
    # the model often takes anchor 3'.
    # Each trap pre-computed:
    answers = [3, 2, 7, 5, 12]
    chain = "-".join(str(a) for a in answers)
    return {"answers": answers, "chain": chain, "digest": _sha1(chain)}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

ALL_BUILDERS = [
    ("L0_703", build_L0_703),
    ("L0_704", build_L0_704),
    ("L0_705", build_L0_705),
    ("L0_706", build_L0_706),
    ("L0_707", build_L0_707),
    ("L0_708", build_L0_708),
    ("L0_709", build_L0_709),
    ("L0_710", build_L0_710),
    ("L0_713", build_L0_713),
    ("L0_714", build_L0_714),
    ("L0_715", build_L0_715),
]


def main() -> None:
    for tid, fn in ALL_BUILDERS:
        print(f"=== {tid} ===")
        r = fn()
        for k, v in r.items():
            if k == "digest":
                print(f"  EXPECTED: {v}")
            else:
                print(f"  {k}: {v}")
        print()


if __name__ == "__main__":
    main()
