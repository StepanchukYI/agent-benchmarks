"""Harden L0_1xx NIAH tasks: inflate haystacks + multi-step + decoys + sha1 pipeline.

Generates ~80-100K token haystacks (~340-400 KB) and overwrites the YAML for
15 NIAH tasks. Each haystack contains N true needles + decoys + filler.

Per-task seed derives from task_id so output is fully deterministic.
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "packages/ab-datasets/fixtures/repos/L0_smoke"
L0_DIR = REPO / "packages/ab-datasets/ab_datasets/L0_foundation"

PLACES = [
    "Anvilford", "Brumcastle", "Corwick", "Dunmore", "Elwick", "Falstead", "Greylock",
    "Hallow", "Idrigil", "Jorrith", "Kelwick", "Larren", "Marrowfen", "Norhall",
    "Olspere", "Penrith", "Quenwick", "Riverstone", "Storra", "Tornmoor", "Underholt",
    "Vyport", "Westcairn", "Xenmore", "Ystwyth", "Zoarwick", "Brenthal", "Felden",
    "Ashford", "Brenswick", "Dunmere", "Saltmoor", "Wenmoor", "Carrick", "Halewick",
    "Ironwell", "Kilthorne", "Maerstone", "Northhollow", "Otherwick",
]
ADJ = [
    "northern", "eastern", "provisional", "historical", "quarterly", "annual",
    "seasonal", "regional", "interim", "transitional", "perennial", "summary",
    "preliminary", "tertiary", "sectional", "marginal", "auxiliary", "consolidated",
]
NOUN = [
    "storage", "frequency", "allocation", "manifest", "register", "schedule",
    "directory", "ledger", "catalogue", "inventory", "rotation", "dispatch",
    "roster", "compendium", "summary", "index", "bulletin",
]
SEASONS = ["spring", "summer", "autumn", "winter"]

# Longer filler templates → more tokens per paragraph
FILLER_TEMPLATES = [
    "The {adj} {noun} of {place} was formally recorded in the {season} {year} catalogue along with seven adjacent {noun2} entries covering the {adj2} oversight period.",
    "According to the {year} field report compiled by the regional bureau, the {noun} index for {place} stood at {val} units after the {season} survey, with {adj} variations noted in subsequent {noun2} addenda.",
    "Regional observers in {place} noted a {adj} pattern of {noun} during the {season} {year} cycle that prompted a {adj2} addendum filed by the {noun2} secretariat for archival reference.",
    "The {place} {noun} board issued a {adj} bulletin for the {year} cycle outlining the {season} review of {noun2} entries flagged for {adj2} reassessment under the standing protocol.",
    "Local archives indicate the {place} {noun} register was last updated in {season} {year} with a {adj} addendum covering {noun2} adjustments approved by the {adj2} review committee.",
    "Field surveys conducted in {season} {year} placed the {place} {adj} {noun} measure at moderate levels with {val} as the reported central tendency for {noun2} sub-categories under continued review.",
    "The {season} {year} edition catalogued the {place} {adj} {noun} systematically alongside {noun2} cross-references and notes on the {adj2} reorganisation completed during the previous reporting interval.",
    "Public records show the {place} {noun} office processed routine filings in {year} with no {adj} exceptions recorded among the {val} entries logged in the {season} bulletin for {noun2} archives.",
    "A summary of the {year} {place} {noun} activity appeared in the {season} compendium, listing {val} {noun2} entries cross-indexed against the {adj} oversight register from the prior cycle.",
    "Field notes from {season} {year} include observations on the {place} {noun} cycle and ancillary {noun2} markers that informed the {adj} review prepared by the regional secretariat.",
    "The {adj} {noun} working group reviewed {place} entries in their {year} session and approved {val} routine {noun2} updates pending the {season} compilation of the consolidated record.",
    "Auditors confirmed the {place} {noun} entries for {year} were properly catalogued and cross-checked against {noun2} duplicates flagged in the {season} review issued by the {adj} verification panel.",
    "A {adj} addendum to the {year} {place} {noun} record was filed in {season} after {val} {noun2} cross-references required formal acknowledgement under the standing documentary protocol.",
    "Independent reviewers noted that {place} {noun} archives from {year} were consistent with {noun2} entries logged in the {season} oversight bulletin under the {adj} review framework.",
    "The {year} {season} compilation of {place} {noun} records included {val} {noun2} cross-references and a {adj} appendix prepared for the regional documentary archive.",
]


def filler_paragraph(rng: random.Random) -> str:
    return rng.choice(FILLER_TEMPLATES).format(
        adj=rng.choice(ADJ), adj2=rng.choice(ADJ),
        noun=rng.choice(NOUN), noun2=rng.choice(NOUN),
        place=rng.choice(PLACES),
        season=rng.choice(SEASONS),
        year=rng.randint(1980, 2020),
        val=round(rng.uniform(10, 999), 1),
    )


TASKS = {
    "L0_101": {
        "category": "signal frequency",
        "unit": "MHz",
        "needles": [
            ("Anvilford", "88.7"), ("Brenthal", "142.3"), ("Corwick", "29.1"),
            ("Dunmore", "77.4"), ("Elwick", "315.8"),
        ],
        "decoy_value_drift": [("Corwick", "29.2"), ("Dunmore", "77.5")],
    },
    "L0_102": {
        "category": "duty officer for",
        "unit": "watch",
        "needles": [
            ("Falstead", "Rena Voss"), ("Greylock", "Pavel Otun"),
            ("Hallow", "Imara Telk"), ("Idrigil", "Sten Vorak"),
            ("Jorrith", "Wren Klost"),
        ],
        "decoy_value_drift": [("Falstead", "Rina Voss"), ("Hallow", "Imara Telc")],
    },
    "L0_103": {
        "category": "warehouse code",
        "unit": "",
        "needles": [
            ("Kelwick", "W-9046"), ("Larren", "W-8253"), ("Marrowfen", "W-2210"),
            ("Norhall", "W-4099"), ("Olspere", "W-5587"),
        ],
        "decoy_value_drift": [("Kelwick", "W-9047"), ("Larren", "W-8254")],
    },
    "L0_104": {
        "category": "critical alert code",
        "unit": "",
        "needles": [
            ("Penrith", "AL-3318"), ("Quenwick", "AL-6741"),
            ("Riverstone", "AL-5582"), ("Storra", "AL-9911"),
            ("Tornmoor", "AL-7740"),
        ],
        "needle_pos_strategy": "head_heavy",
    },
    "L0_105": {
        "category": "mid-band identifier",
        "unit": "",
        "needles": [
            ("Underholt", "MB-1108"), ("Vyport", "MB-2207"), ("Westcairn", "MB-3306"),
            ("Xenmore", "MB-4405"), ("Ystwyth", "MB-5504"),
        ],
        "needle_pos_strategy": "mid_heavy",
    },
    "L0_106": {
        "category": "warning system dB",
        "unit": "dB",
        "needles": [
            ("Vyport", "92.4"), ("Saltmoor", "88.0"), ("Wenmoor", "104.7"),
            ("Carrick", "76.3"), ("Halewick", "111.2"),
        ],
        "needle_pos_strategy": "tail_heavy",
    },
    "L0_107": {
        "category": "configuration key",
        "unit": "",
        "needles": [
            ("Ironwell", "K-2210"), ("Jorrith", "K-3306"), ("Kilthorne", "K-4499"),
            ("Larren", "K-5588"), ("Maerstone", "K-6677"),
        ],
    },
    "L0_108": {
        "category": "founding director",
        "unit": "",
        "needles": [
            ("Northhollow", "Eira Vass"), ("Otherwick", "Lin Karoth"),
            ("Penrith", "Voll Brenmark"), ("Quenwick", "Sten Olav"),
        ],
        "decoy_value_drift": [("Northhollow", "Eira Vasc"), ("Penrith", "Voll Brenmork")],
    },
    "L0_109": {
        "category": "current value of x",
        "unit": "",
        "needles": [
            ("step-1", "11"), ("step-2", "23"), ("step-3", "47"),
            ("step-4", "94"), ("step-5", "188"),
        ],
        "is_sequence": True,
    },
    "L0_110": {
        "category": "ranking note",
        "unit": "",
        "needles": [
            ("Riverstone", "top-1"), ("Storra", "top-2"), ("Tornmoor", "top-3"),
            ("Underholt", "top-4"), ("Vyport", "top-5"),
        ],
    },
    "L0_120": {
        "category": "treasury vault code",
        "unit": "",
        "needles": [
            ("Westcairn", "TV-8014"), ("Xenmore", "TV-2207"), ("Ystwyth", "TV-9933"),
            ("Zoarwick", "TV-5582"), ("Anvilford", "TV-7740"),
        ],
    },
    "L0_121": {
        "category": "warehouse code",
        "unit": "",
        "needles": [
            ("Anvilford", "W-9046"), ("Brumcastle", "W-8253"), ("Felden", "W-2210"),
            ("Greylock", "W-4099"), ("Marrowfen", "W-5587"), ("Storra", "W-3318"),
            ("Vyport", "W-6741"),
        ],
        "decoy_value_drift": [
            ("Anvilford", "W-9047"), ("Brumcastle", "W-8254"), ("Felden", "W-2211"),
        ],
    },
    "L0_122": {
        "category": "aurora observation date",
        "unit": "",
        "needles": [
            ("Northhollow", "1992-04-17"), ("Otherwick", "1995-09-22"),
            ("Penrith", "2001-02-08"), ("Quenwick", "2014-11-30"),
            ("Riverstone", "2020-06-14"),
        ],
        "needle_pos_strategy": "tail_heavy",
    },
    "L0_123": {
        "category": "deputy commander",
        "unit": "",
        "needles": [
            ("Storra", "Mara Quell"), ("Tornmoor", "Jen Karoth"),
            ("Underholt", "Wim Lossen"), ("Vyport", "Karra Mott"),
            ("Westcairn", "Rolf Tanner"), ("Xenmore", "Pia Veld"),
        ],
        "decoy_value_drift": [("Storra", "Mara Quill"), ("Tornmoor", "Jen Karroth")],
    },
    "L0_124": {
        "category": "secure key id",
        "unit": "",
        "needles": [
            ("Hallow", "SK-1100"), ("Idrigil", "SK-2200"), ("Jorrith", "SK-3300"),
            ("Kelwick", "SK-4400"), ("Larren", "SK-5500"),
        ],
        "decoy_value_drift": [
            ("Hallow", "SK-1101"), ("Idrigil", "SK-2201"), ("Jorrith", "SK-3301"),
            ("Kelwick", "SK-4401"), ("Larren", "SK-5501"),
        ],
    },
}


def build_haystack(task_id: str, cfg: dict) -> tuple[str, str, str]:
    """Generate haystack + return (text, expected_answer, joined_string)."""
    seed = int(hashlib.sha1(task_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    n_paragraphs = 2500  # ~150 bytes/paragraph * 2500 = ~375KB ≈ 90K tokens
    category = cfg["category"]
    unit = cfg.get("unit", "")
    is_sequence = cfg.get("is_sequence", False)

    needle_tuples = [(e, v) for e, v in cfg["needles"]]
    decoys = cfg.get("decoy_value_drift", [])

    paragraphs = [filler_paragraph(rng) for _ in range(n_paragraphs)]

    strategy = cfg.get("needle_pos_strategy", "balanced")
    n = len(needle_tuples)
    if strategy == "head_heavy":
        positions = [int(n_paragraphs * 0.01 * (i + 1)) for i in range(n)]
    elif strategy == "mid_heavy":
        positions = [int(n_paragraphs * (0.45 + 0.02 * i)) for i in range(n)]
    elif strategy == "tail_heavy":
        positions = [int(n_paragraphs * (0.93 + 0.012 * i)) for i in range(n)]
    elif is_sequence:
        positions = [int(n_paragraphs * (0.1 + 0.18 * i)) for i in range(n)]
    else:
        step = n_paragraphs // (n + 1)
        positions = [step * (i + 1) for i in range(n)]
        if positions:
            positions[-1] = int(n_paragraphs * 0.97)

    used = set()
    if is_sequence:
        for (step_id, value), pos in zip(needle_tuples, positions, strict=True):
            used.add(pos)
            paragraphs[pos] = (
                f"Sequence checkpoint {step_id}: the {category} is now set to {value} "
                f"as recorded by the audit subsystem during the routine reconciliation pass."
            )
    else:
        for (entity, value), pos in zip(needle_tuples, positions, strict=True):
            used.add(pos)
            v_str = f"{value} {unit}".strip()
            paragraphs[pos] = (
                f"The {entity} {category} is {v_str}, as confirmed by the regional "
                f"verification panel during the quarterly oversight review."
            )

    rng2 = random.Random(seed ^ 0xdead)
    for entity, drift_value in decoys:
        for _ in range(50):
            p = rng2.randrange(n_paragraphs)
            if p not in used:
                used.add(p)
                v_str = f"{drift_value} {unit}".strip()
                paragraphs[p] = (
                    f"A preliminary draft noted that the {entity} {category} might be {v_str}, "
                    f"however this entry was superseded by a subsequent revision and should not "
                    f"be used as the canonical value."
                )
                break

    haystack = "\n\n".join(paragraphs) + "\n"

    if is_sequence:
        expected = needle_tuples[-1][1]
        joined = expected
    else:
        sorted_needles = sorted(needle_tuples, key=lambda x: x[0])
        # Value-with-unit (the form models will see in the haystack) — keeps
        # spec unambiguous (L0_101 caught this: model wrote "88.7 MHz" but
        # generator joined "88.7" without unit, mismatch was spec ambiguity).
        def fmt(v):
            return f"{v} {unit}".strip()
        joined = "|".join(f"{e}={fmt(v)}" for e, v in sorted_needles)
        expected = hashlib.sha1(joined.encode("utf-8")).hexdigest()

    return haystack, expected, joined


def yaml_for(task_id: str, cfg: dict, expected: str, joined: str, haystack_bytes: int) -> str:
    is_sequence = cfg.get("is_sequence", False)
    n_needles = len(cfg["needles"])
    category = cfg["category"]
    approx_tokens = haystack_bytes // 4

    # ENTITY names only — values must be discovered from the haystack.
    # Leaking values lets the model skip reading entirely (verified empirically:
    # opus took `Anvilford=W-9046|...` from the description and never read haystack).
    needle_entity_list = ", ".join(e for e, _ in cfg["needles"])
    first_entity = cfg["needles"][0][0]
    cat_word = category.split()[0]

    if is_sequence:
        title = f"NIAH sequence rebind ({n_needles} steps in {approx_tokens // 1000}K-token haystack)"
        description_body = (
            f"  The haystack `haystack.txt` is {haystack_bytes:,} bytes\n"
            f"  (~{approx_tokens // 1000}K tokens) of dense bureaucratic filler.\n"
            f"\n"
            f"  Buried in it are exactly {n_needles} sequential rebind checkpoints\n"
            f"  of the form:\n"
            f"\n"
            f'      "Sequence checkpoint <step-id>: the {category} is now set to <value>..."\n'
            f"\n"
            f"  The checkpoints are spread across the document. They are NOT in\n"
            f"  position order — you must scan the FULL document, collect every\n"
            f"  checkpoint, sort by step-id, then take the value of the LAST one\n"
            f"  (step-{n_needles}). That is the final bound value.\n"
            f"\n"
            f"  Output ONLY the final integer value as the sole final message.\n"
            f"  No prose, no prefix, no quotes, no markdown, no trailing newline.\n"
            f"\n"
            f"  Failure modes:\n"
            f"    - taking the first checkpoint found instead of step-{n_needles},\n"
            f"    - missing a checkpoint (incomplete scan of the long haystack),\n"
            f"    - emitting any prose or `step=` prefix around the value.\n"
        )
        scorer_name = "exact_needle_value"
        forbidden_yaml = (
            '          - "checkpoint"\n'
            '          - "step-"\n'
            '          - "value is"\n'
        )
        criteria = "Final message is the final rebound integer value."
    else:
        title = f"NIAH hardened: {n_needles} needles + decoys + sha1 pipeline ({approx_tokens // 1000}K tokens)"
        description_body = (
            f"  The haystack `haystack.txt` is {haystack_bytes:,} bytes\n"
            f"  (~{approx_tokens // 1000}K tokens) of dense bureaucratic filler.\n"
            f"\n"
            f"  STEP 1 — Extract.\n"
            f'    Read haystack.txt. Find every paragraph that contains the phrase\n'
            f'    "{category}" used as a FACTUAL statement (look for the\n'
            f'    confirmed-by-regional-verification-panel phrasing, NOT draft /\n'
            f'    preliminary / superseded entries — those are decoys to exclude).\n'
            f"\n"
            f"    There are exactly {n_needles} TRUE (entity, value) pairs to\n"
            f"    collect. Each entity appears in exactly ONE confirmed paragraph;\n"
            f"    some entities ALSO appear in a DECOY paragraph (marked \"draft\"\n"
            f'    or "preliminary, superseded") — those must be EXCLUDED.\n'
            f"\n"
            f"    Entity names you must find values for (values are NOT given —\n"
            f"    discover each entity's <value> from the haystack itself):\n"
            f"      {needle_entity_list}\n"
            f"\n"
            f"  STEP 2 — Sort.\n"
            f"    Sort the (entity, value) pairs alphabetically by entity name.\n"
            f"\n"
            f"  STEP 3 — Format.\n"
            f"    Build a SINGLE string by joining the pairs as `<entity>=<value>`\n"
            f"    with the literal `|` separator (NO whitespace around `|`).\n"
            f"    The `<value>` is exactly as printed in the haystack INCLUDING\n"
            f"    any unit suffix (e.g. `88.7 MHz`, not just `88.7`).\n"
            f"\n"
            f"  STEP 4 — Hash.\n"
            f"    Compute the lowercase hex SHA-1 of the UTF-8 bytes of the joined\n"
            f"    string (no trailing newline). Emit ONLY the 40-character hex\n"
            f"    digest as the final assistant message. No prefix, no quotes, no\n"
            f"    markdown, no trailing newline.\n"
            f"\n"
            f"    You must actually compute the hash — the digest is NOT in this\n"
            f"    description. Use `Bash` (`shasum -a 1` or `sha1sum`) or Python\n"
            f"    (`hashlib.sha1(s.encode()).hexdigest()`).\n"
            f"\n"
            f"  Failure modes:\n"
            f"    - including a decoy value (draft/superseded entry),\n"
            f"    - missing a needle (especially the tail-depth ones),\n"
            f"    - emitting the joined string instead of the sha1,\n"
            f"    - wrong sort order (must be alphabetical by entity name),\n"
            f"    - emitting prose surrounding the digest.\n"
        )
        scorer_name = "four_needles_ordered"
        forbidden_yaml = (
            f'          - "{first_entity}"\n'
            f'          - "{cat_word}"\n'
            f'          - "="\n'
        )
        criteria = "Final message is the 40-char lowercase hex sha1 of the pipe-joined alphabetical pairs."

    return (
        f"id: {task_id}\n"
        f"layer: L0\n"
        f"suite: long-context-niah\n"
        f'title: "{title}"\n'
        f"description: |\n"
        f"{description_body}"
        f'fixture_ref: "fixtures/repos/L0_smoke/{task_id}/"\n'
        f"\n"
        f"config:\n"
        f"  required_tier: T0\n"
        f"  recommended_tier: T0\n"
        f"  also_run_on: [T2]\n"
        f"  requires: {{skills: [], mcps: [], vault_state: {{}}}}\n"
        f"\n"
        f"scorer_chain:\n"
        f"  - name: {scorer_name}\n"
        f"    kind: deterministic\n"
        f"    config:\n"
        f'      source_file: "haystack.txt"\n'
        f"      assertions:\n"
        f"        - kind: final_assistant_message_equals\n"
        f'          expected: "{expected}"\n'
        f"          trim_whitespace: true\n"
        f"        - kind: final_assistant_message_does_not_contain\n"
        f"          forbidden:\n"
        f"{forbidden_yaml}"
        f"\n"
        f"  - name: privacy_check\n"
        f"    kind: privacy_check\n"
        f'    config: {{patterns_path: "docs/privacy-patterns.yaml"}}\n'
        f"\n"
        f"  - name: tool_skill\n"
        f"    kind: deterministic\n"
        f"    config: {{max_tool_calls: 8, pass_threshold: 0.8}}\n"
        f"\n"
        f"  - name: context_efficiency\n"
        f"    kind: deterministic\n"
        f"    config: {{target_tokens: 60000, max_tokens: 150000, pass_threshold: 0.6}}\n"
        f"\n"
        f"  - name: latency_cost\n"
        f"    kind: deterministic\n"
        f"    config: {{target_ms: 90000, max_ms: 240000, pass_threshold: 0.6}}\n"
        f"\n"
        f"acceptance_criteria:\n"
        f'  - "{criteria}"\n'
        f'  - "No decoy / draft / superseded values are included."\n'
        f'  - "Privacy scan zero hits."\n'
        f"\n"
        f"weights:\n"
        f"  correctness: 0.70\n"
        f"  tool_skill: 0.10\n"
        f"  context_efficiency: 0.10\n"
        f"  latency_cost: 0.05\n"
        f"  memory_specific: 0.05\n"
        f"\n"
        f"difficulty: hard\n"
        f"visibility: public\n"
        f"trust_tier_ceiling: verified\n"
        f"\n"
        f"tags:\n"
        f"  - L0\n"
        f"  - long-context\n"
        f"  - niah\n"
        f"  - multi-needle\n"
        f"  - decoy\n"
        f"  - hash\n"
        f"  - frontier\n"
        f"  - deterministic\n"
        f"  - reasoning-sensitive\n"
        f"  - byte-exact-output\n"
        f"  - output-normalization-sensitive\n"
        f"  - context-window-sensitive\n"
        f"  - multi-step\n"
    )


def main() -> int:
    for task_id, cfg in TASKS.items():
        candidates = list(L0_DIR.glob(f"{task_id}-*.yaml"))
        if not candidates:
            print(f"  SKIP {task_id}: no YAML found")
            continue
        yaml_path = candidates[0]
        fixture_dir = FIXTURES / task_id
        fixture_dir.mkdir(parents=True, exist_ok=True)

        haystack, expected, joined = build_haystack(task_id, cfg)
        haystack_bytes = len(haystack.encode("utf-8"))

        (fixture_dir / "haystack.txt").write_text(haystack, encoding="utf-8")
        yaml_path.write_text(yaml_for(task_id, cfg, expected, joined, haystack_bytes), encoding="utf-8")

        print(f"  {task_id}: haystack={haystack_bytes:,} bytes (~{haystack_bytes // 4:,} tokens) expected={expected[:16]}…")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
