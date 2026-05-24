"""Lever B fixture generator — Group 2 (file-ops) + helpers for other groups.

Generates deterministic fixtures and prints the expected values that the
corresponding YAMLs must reference. Idempotent: re-running produces
byte-identical fixtures.

Run:
    uv run python scripts/build_lever_b_fixtures.py
"""

from __future__ import annotations

import hashlib
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "packages" / "ab-datasets" / "fixtures" / "repos" / "L0_smoke"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)


# ---------------------------------------------------------------------------
# L0_001 — preserve-sentinels fixture
# ---------------------------------------------------------------------------

def build_L0_001() -> dict:
    d = FIXTURES / "L0_001"
    _write(d / ".keep", b"X")
    readme = (
        "FIXTURE README — DO NOT MODIFY.\n"
        "This file is a sentinel for L0_001. Any byte change is a failure.\n"
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do "
        "eiusmod tempor incididunt ut labore et dolore magna aliqua.\n"
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris "
        "nisi ut aliquip ex ea commodo consequat.\n"
    )
    _write(d / "README.fixture", readme)
    rng = random.Random(20260524)
    seed_bytes = bytes(rng.randrange(0, 256) for _ in range(64))
    _write(d / "data" / "seed.bin", seed_bytes)
    return {"keep_bytes": "X", "readme_len": len(readme), "seed_sha": hashlib.sha256(seed_bytes).hexdigest()}


# ---------------------------------------------------------------------------
# L0_002 — three-file rotation (no symlinks; symlinks break on Windows test runners)
# ---------------------------------------------------------------------------

def build_L0_002() -> dict:
    d = FIXTURES / "L0_002"
    _write(d / "a.py", "def greet():\n    return 'hello from a'\n")
    _write(d / "b.py", "def greet():\n    return 'hello from b'\n")
    _write(d / "c.py", "def greet():\n    return 'hello from c'\n")
    return {"rotation": "a->b->c->a (content-wise)"}


# ---------------------------------------------------------------------------
# L0_007 — read-and-stitch (4 non-contiguous line ranges)
# ---------------------------------------------------------------------------

def build_L0_007() -> dict:
    d = FIXTURES / "L0_007"
    lines = [f"line {i:04d}" for i in range(1, 2001)]
    _write(d / "numbered.txt", "\n".join(lines) + "\n")
    # Required ranges (1-indexed inclusive): [10,15], [500,505], [1000,1005], [1900,1905]
    out_lines = []
    for a, b in [(10, 15), (500, 505), (1000, 1005), (1900, 1905)]:
        out_lines.extend(lines[a - 1: b])
    expected = "\n".join(out_lines)
    return {"expected": expected}


# ---------------------------------------------------------------------------
# L0_008 — idempotent version bump across 5 JSON files
# ---------------------------------------------------------------------------

def build_L0_008() -> dict:
    d = FIXTURES / "L0_008"
    files = ["api.json", "core.json", "ui.json", "db.json", "cli.json"]
    for f in files:
        _write(d / f, '{"version": "0.1.0", "name": "' + f.replace(".json", "") + '"}\n')
    expected = {
        f: '{"version": "0.2.0", "name": "' + f.replace(".json", "") + '"}\n'
        for f in files
    }
    return {"expected_files": expected}


# ---------------------------------------------------------------------------
# L0_020 — 3-step bash chain (filter -> dedupe -> count)
# ---------------------------------------------------------------------------

def build_L0_020() -> dict:
    d = FIXTURES / "L0_020"
    rows = [
        # Status lines (KEEP): start with "STATUS:"
        "STATUS: alpha-build OK",
        "STATUS: beta-build OK",
        "STATUS: alpha-build OK",     # dup
        "STATUS: gamma-build FAIL",
        "INFO: kicking off run",      # skip (not STATUS)
        "STATUS: delta-build OK",
        "STATUS: beta-build OK",      # dup
        "DEBUG: registry warm",       # skip
        "STATUS: epsilon-build SKIP",
        "STATUS: zeta-build OK",
        "STATUS: alpha-build OK",     # dup again
        "STATUS: omicron-build OK",
        "WARN: clock drift",          # skip
        "STATUS: pi-build OK",
        "STATUS: epsilon-build SKIP",  # dup
        "INFO: shutting down",        # skip
    ]
    _write(d / "raw.txt", "\n".join(rows) + "\n")
    # Filter to STATUS lines, dedupe preserving first-seen order, count.
    filtered = [r for r in rows if r.startswith("STATUS:")]
    seen = set()
    deduped = []
    for r in filtered:
        if r not in seen:
            seen.add(r)
            deduped.append(r)
    return {
        "expected_filtered": "\n".join(filtered) + "\n",
        "expected_deduped": "\n".join(deduped) + "\n",
        "expected_count": str(len(deduped)),  # = 8
    }


# ---------------------------------------------------------------------------
# L0_021 — CSV sum with NaN + locale-formatted numbers mixed in
# ---------------------------------------------------------------------------

def build_L0_021() -> dict:
    d = FIXTURES / "L0_021"
    rows = [
        ("alpha", "10"),
        ("beta", "NaN"),
        ("gamma", "25"),
        ("delta", ""),
        ("epsilon", "-5"),
        ("zeta", "abc"),
        ("eta", "3.14"),
        ("theta", "1_000"),
        ("iota", "100"),
        ("kappa", "1,234"),
        ("lambda", "200"),
        ("mu", "-50"),
    ]
    csv_text = "name,amount\n" + "\n".join(f"{n},{v}" for n, v in rows) + "\n"
    _write(d / "values.csv", csv_text)
    # Per spec: valid = parseable by Python's float() OR int() after removing
    # underscores only. Invalid = NaN, empty, alpha strings, European comma.
    valid_total = 0.0
    for _, v in rows:
        s = v.replace("_", "")
        try:
            f = float(s)
        except (ValueError, TypeError):
            continue
        if f != f:  # NaN
            continue
        valid_total += f
    return {"expected_sum": f"{valid_total:.2f}"}


# ---------------------------------------------------------------------------
# L0_022 — sha256 of a byte range selected by a separate step
# ---------------------------------------------------------------------------

def build_L0_022() -> dict:
    d = FIXTURES / "L0_022"
    rng = random.Random(20260524)
    data = bytes(rng.randrange(0, 256) for _ in range(256))
    _write(d / "data.bin", data)
    # Range [64, 128) — 64 bytes from offset 64.
    subset = data[64:128]
    return {"expected_digest": hashlib.sha256(subset).hexdigest()}


# ---------------------------------------------------------------------------
# Group 3 — long-context tasks
# ---------------------------------------------------------------------------

_DISTRACTOR_LINES = [
    "Students of {name} catalogued {color} stones throughout the {place} valley.",
    "A traveller named {name} once described the {color} cliffs above the bay.",
    "In the {color} dusk, the lighthouse at {place} fell silent for an hour.",
    "Researchers at the {place} institute reported that {animal} populations remained stable.",
    "The {color} crane circled the {place} three times before landing.",
    "An old map labels the {color} ridge east of {place} as the {animal}'s pass.",
    "The {animal} crossed the {place} under a {color} sky.",
    "Local archives in {place} list {name} as the keeper of the {color} chest.",
    "The festival at {place} featured a {color} flag carried by a single {animal}.",
    "The {animal} from {place} prefers {color} berries during the dry season.",
]
_NAMES = ["Toren", "Idris", "Lyra", "Roen", "Kael", "Mira", "Volker", "Sevda", "Anya", "Brenn"]
_COLORS = ["amber", "azure", "emerald", "russet", "indigo", "saffron", "viridian", "umber", "slate", "cerise"]
_PLACES = ["Saltmoor", "Vyport", "Brumcastle", "Cantillon", "Greylock", "Eldermere", "Thalin", "Anvilford", "Riftwood"]
_ANIMALS = ["fox", "raven", "ibis", "lynx", "otter", "heron", "marten", "hare", "deer", "moth"]


def _distractor_paragraph(rng: random.Random) -> str:
    """One paragraph of 4-6 distractor sentences."""
    n = rng.randint(4, 6)
    out: list[str] = []
    for _ in range(n):
        tmpl = rng.choice(_DISTRACTOR_LINES)
        out.append(tmpl.format(
            name=rng.choice(_NAMES),
            color=rng.choice(_COLORS),
            place=rng.choice(_PLACES),
            animal=rng.choice(_ANIMALS),
        ))
    return " ".join(out)


def _build_haystack(rng: random.Random, total_paragraphs: int, needles: list[tuple[int, str]]) -> str:
    """Build a haystack with `total_paragraphs`, injecting each needle at the
    specified 0-based paragraph index. needles = [(idx, text), ...]."""
    placed = {idx: text for idx, text in needles}
    paragraphs: list[str] = []
    for i in range(total_paragraphs):
        if i in placed:
            paragraphs.append(placed[i])
        else:
            paragraphs.append(_distractor_paragraph(rng))
    return "\n\n".join(paragraphs) + "\n"


# L0_101 — RULER NIAH @ depth 99%
def build_L0_101() -> dict:
    d = FIXTURES / "L0_101"
    rng = random.Random(101)
    needle = "The Tornmoor signal frequency is 88.7 MHz, recorded in the spring catalogue."
    paragraphs = 220  # ~ rough 32k tokens of distractor + 1 needle paragraph
    idx = int(paragraphs * 0.99)
    haystack = _build_haystack(rng, paragraphs, [(idx, needle)])
    _write(d / "haystack.txt", haystack)
    return {"expected": "88.7 MHz", "needle_at_para": idx, "n_paragraphs": paragraphs}


# L0_104 — depth-randomized NIAH (single needle)
def build_L0_104() -> dict:
    d = FIXTURES / "L0_104"
    rng = random.Random(104)
    needle = "The Vyport council elected Anya as harbour-master in the year 1843."
    paragraphs = 90
    # Random depth ∈ [30, 70] for this seed
    idx = rng.randint(int(paragraphs * 0.30), int(paragraphs * 0.70))
    haystack = _build_haystack(rng, paragraphs, [(idx, needle)])
    _write(d / "haystack.txt", haystack)
    return {"expected": "1843", "needle_at_para": idx}


# L0_105 — 4-needle simultaneous NIAH
def build_L0_105() -> dict:
    d = FIXTURES / "L0_105"
    rng = random.Random(105)
    needles = [
        (15, "The Saltmoor lighthouse foghorn rings at 32 Hz on stormy nights."),
        (37, "The Brumcastle clock tower chimes every 17 minutes after midnight."),
        (62, "The Greylock observatory tracks comet 41P with daily precision."),
        (88, "The Anvilford forge maintains 1923 degrees Celsius during the autumn run."),
    ]
    haystack = _build_haystack(rng, 110, needles)
    _write(d / "haystack.txt", haystack)
    # Question: list (Anvilford, Brumcastle, Greylock, Saltmoor) numbers in alphabetical order of place.
    expected = "1923, 17, 41, 32"
    return {"expected": expected, "needles": [(i, t) for i, t in needles]}


# L0_106 — near-collision needle (whole-noun-phrase match required)
def build_L0_106() -> dict:
    d = FIXTURES / "L0_106"
    rng = random.Random(106)
    target = "The Vyport HARBOUR FOG warning system is rated 92.4 dB."
    decoys_lines = [
        "The Vyport harbour map shows three berths along the west pier.",
        "The Vyport harbour council met last spring to discuss dredging.",
        "The Vyport fog horn was retired in 1971.",
        "The Saltmoor harbour fog warning system is rated 88.0 dB.",
        "The Vyport HARBOUR LIGHT system is rated 145.0 cd.",
    ]
    # Place decoys at random; target at depth 50%.
    paragraphs = 80
    rng2 = random.Random(106)
    positions = rng2.sample(range(paragraphs), len(decoys_lines) + 1)
    placements = {positions[-1]: target}
    for i, line in enumerate(decoys_lines):
        placements[positions[i]] = line
    haystack = _build_haystack(rng, paragraphs, list(placements.items()))
    _write(d / "haystack.txt", haystack)
    return {"expected": "92.4 dB", "target_text": target}


# L0_110 — common words top-5 with case-fold ties broken by position
def build_L0_110() -> dict:
    d = FIXTURES / "L0_110"
    # Design: handcrafted small passage where ties exist on count.
    text = (
        "Alpha bravo alpha charlie delta echo alpha echo Foxtrot Alpha. "
        "Charlie bravo charlie delta delta echo. "
        "Echo Foxtrot Foxtrot alpha bravo charlie. "
        "Delta delta charlie bravo Foxtrot echo. "
        "Alpha bravo charlie delta echo Foxtrot."
    )
    _write(d / "passage.txt", text)
    # Words case-folded:
    # alpha: positions [0,2,6,9,14] -> 5 times? let's count more carefully.
    # Actually let me just compute it.
    import re
    tokens = re.findall(r"[A-Za-z]+", text)
    folded = [t.lower() for t in tokens]
    counts: dict[str, int] = {}
    first_pos: dict[str, int] = {}
    for i, w in enumerate(folded):
        counts[w] = counts.get(w, 0) + 1
        first_pos.setdefault(w, i)
    # Sort: by -count, then by first_pos ascending.
    sorted_words = sorted(counts.keys(), key=lambda w: (-counts[w], first_pos[w]))
    top5 = sorted_words[:5]
    expected = ",".join(top5)
    return {"expected": expected, "counts": dict(sorted(counts.items()))}


# L0_202 — sum with 3 word-numbers and 2 negatives
def build_L0_202() -> dict:
    d = FIXTURES / "L0_202"
    rng = random.Random(202)
    # 23 entries: 18 numerals, 3 in words, 2 negatives.
    numerals = [3, 7, 12, 4, 19, 25, 8, 11, 6, 2, 14, 30, 9, 5, 17, 1, 23, 100]
    words = [("twelve", 12), ("thirty-four", 34), ("eighty-one", 81)]
    negatives = [-7, -15]
    expected_sum = sum(numerals) + sum(v for _, v in words) + sum(negatives)
    # Build entries
    entries: list[str] = []
    for n in numerals:
        entries.append(f"Inventory log entry {n} units shipped.")
    for txt, _ in words:
        entries.append(f"Inventory log entry {txt} units shipped.")
    for n in negatives:
        entries.append(f"Inventory log entry {n} units shipped.")
    rng.shuffle(entries)
    # Mix into 65 distractor paragraphs
    paragraphs = 65
    # Place entries at 23 random non-overlapping paragraph slots
    slots = rng.sample(range(paragraphs), 23)
    placements = [(s, entries[i]) for i, s in enumerate(slots)]
    haystack = _build_haystack(rng, paragraphs, placements)
    _write(d / "haystack.txt", haystack)
    return {"expected": str(expected_sum), "n_entries": 23}


# L0_502 — verbatim among near-duplicates (punctuation-only differences)
def build_L0_502() -> dict:
    d = FIXTURES / "L0_502"
    # 5 near-duplicate paragraphs differing only in punctuation; exactly ONE
    # matches the user's quote verbatim. The user asks: return only the
    # paragraph that matches the quote, byte-for-byte.
    paragraphs = [
        "The bell at Saltmoor tolls thrice at dusk; its echo is heard across the bay.",
        "The bell at Saltmoor tolls thrice at dusk, its echo is heard across the bay.",
        "The bell at Saltmoor tolls thrice at dusk: its echo is heard across the bay.",
        "The bell at Saltmoor tolls thrice at dusk — its echo is heard across the bay.",
        "The bell at Saltmoor tolls thrice at dusk. Its echo is heard across the bay.",
    ]
    # Target = index 2 (colon)
    target_idx = 2
    text = "Source paragraphs:\n\n" + "\n\n".join(f"P{i+1}: {p}" for i, p in enumerate(paragraphs)) + "\n"
    _write(d / "source.txt", text)
    return {"expected": paragraphs[target_idx], "target_idx": target_idx + 1}


# L0_507 — three statements with two-step transitivity inconsistency
def build_L0_507() -> dict:
    d = FIXTURES / "L0_507"
    statements = (
        "Statement 1: Alia is older than Boris.\n"
        "Statement 2: Boris is older than Cyan.\n"
        "Statement 3: Cyan is older than Alia.\n"
    )
    _write(d / "statements.txt", statements)
    return {"expected": "Statement 3"}


# ---------------------------------------------------------------------------
# Group 4 — multi-turn tool-use / state-diff tasks (simulated via fixture
# seeds + workdir state, the same idiom L0_310 already uses).
# ---------------------------------------------------------------------------

# L0_301 — 3-step state dialog with derived values
def build_L0_301() -> dict:
    d = FIXTURES / "L0_301"
    users = [
        {"id": "U-001", "name": "Alia", "age": 32, "email": "alia@example.com"},
        {"id": "U-002", "name": "Boris", "age": 47, "email": "boris@example.com"},
        {"id": "U-003", "name": "Cyan", "age": 29, "email": "cyan@example.com"},
    ]
    import json
    _write(d / "seed" / "users.json", json.dumps(users, indent=2) + "\n")
    # Step 1: find oldest by age.
    oldest = max(users, key=lambda u: u["age"])  # Boris
    oldest_record = {
        "id": oldest["id"],
        "name": oldest["name"],
        "age": oldest["age"],
    }
    # Step 2: sha256 of the name (case-sensitive, no newline).
    name_digest = hashlib.sha256(oldest["name"].encode("utf-8")).hexdigest()
    # Step 3: summary JSON.
    summary = {
        "oldest_id": oldest["id"],
        "name_sha256": name_digest,
        "age": oldest["age"],
    }
    expected_oldest = json.dumps(oldest_record, separators=(",", ":"))
    expected_summary = json.dumps(summary, separators=(",", ":"))
    return {
        "expected_oldest_json": expected_oldest,
        "expected_hash": name_digest,
        "expected_summary_json": expected_summary,
    }


# L0_302 — optional-arg gating by content of prior step
def build_L0_302() -> dict:
    d = FIXTURES / "L0_302"
    import json
    policy = {"requires_priority": True, "default_priority": "high"}
    _write(d / "seed" / "policy.json", json.dumps(policy, indent=2) + "\n")
    # If requires_priority is True, decision MUST include the priority field.
    decision = {"action": "ack", "priority": policy["default_priority"]}
    return {"expected_decision_json": json.dumps(decision, separators=(",", ":"))}


# L0_303 — strict ordered match across 3 named steps + plausible distractor files
def build_L0_303() -> dict:
    d = FIXTURES / "L0_303"
    _write(d / "seed" / "stage.txt", "init\n")
    # Distractors present in fixture that the agent must NOT touch.
    _write(d / "decoy" / "stage_other.txt", "untouched\n")
    _write(d / "decoy" / "stage.txt.bak", "untouched\n")
    return {
        "expected_stage_after_step1": "build",
        "expected_stage_after_step2": "test",
        "expected_stage_after_step3": "ship",
    }


# L0_307 — array with mixed valid + invalid items, must filter
def build_L0_307() -> dict:
    d = FIXTURES / "L0_307"
    import json
    items = [
        {"id": 1, "amount": 12.5, "currency": "USD"},
        {"id": 2, "amount": "abc", "currency": "USD"},   # invalid amount type
        {"id": 3, "amount": 20.0, "currency": "USD"},
        {"id": 4, "amount": 5.0},                         # missing currency
        {"id": 5, "amount": -7.0, "currency": "USD"},     # negative valid
        {"id": 6, "amount": 100.0, "currency": "BTC"},    # forbidden currency
        {"id": 7, "amount": 33.33, "currency": "USD"},
        {"id": 8, "amount": None, "currency": "USD"},     # null amount
    ]
    _write(d / "seed" / "items.json", json.dumps(items, indent=2) + "\n")
    valid_ids = [i["id"] for i in items
                 if isinstance(i.get("amount"), (int, float))
                 and not isinstance(i.get("amount"), bool)
                 and i.get("currency") == "USD"]
    return {
        "expected_filtered_ids": valid_ids,  # [1, 3, 5, 7]
        "expected_count": len(valid_ids),
        "expected_sum_usd": sum(i["amount"] for i in items
                                if i["id"] in valid_ids),
    }


# L0_311 — parallel calls with shared output-key collision, distinct arg paths required
def build_L0_311() -> dict:
    d = FIXTURES / "L0_311"
    import json
    targets = [
        {"slot": "a", "value": "alpha"},
        {"slot": "b", "value": "beta"},
        {"slot": "c", "value": "gamma"},
        {"slot": "d", "value": "delta"},
    ]
    _write(d / "seed" / "targets.json", json.dumps(targets, indent=2) + "\n")
    expected = {t["slot"]: t["value"] for t in targets}
    return {"expected_files": {f"out/slot_{k}.txt": v for k, v in expected.items()}}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

BUILDERS = {
    "L0_001": build_L0_001,
    "L0_002": build_L0_002,
    "L0_007": build_L0_007,
    "L0_008": build_L0_008,
    "L0_020": build_L0_020,
    "L0_021": build_L0_021,
    "L0_022": build_L0_022,
    # Group 3
    "L0_101": build_L0_101,
    "L0_104": build_L0_104,
    "L0_105": build_L0_105,
    "L0_106": build_L0_106,
    "L0_110": build_L0_110,
    "L0_202": build_L0_202,
    "L0_502": build_L0_502,
    "L0_507": build_L0_507,
    # Group 4
    "L0_301": build_L0_301,
    "L0_302": build_L0_302,
    "L0_303": build_L0_303,
    "L0_307": build_L0_307,
    "L0_311": build_L0_311,
}


def main() -> None:
    for tid, fn in BUILDERS.items():
        print(f"\n=== {tid} ===")
        info = fn()
        for k, v in info.items():
            if isinstance(v, str) and len(v) > 200:
                print(f"  {k} (len={len(v)}): {v[:120]}...")
            elif isinstance(v, dict):
                print(f"  {k}:")
                for kk, vv in v.items():
                    print(f"    {kk}: {repr(vv)[:120]}")
            else:
                print(f"  {k}: {repr(v)[:200]}")


if __name__ == "__main__":
    main()
