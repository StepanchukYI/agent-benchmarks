"""Generate the 50 seed facts and the retrieval ground-truth for L1_003.

Maintainer-run only. CI does not invoke this script; the materialized
fact_NNN.json files and ground_truth_retrieval.json are checked in.
"""

from __future__ import annotations

import json
from pathlib import Path

# (subject, predicate, object, valid_from)
# 50 facts. The first 7 are the relevant set for the query "what tools
# does Evgeniy use for coding"; the rest are distractors.
FACTS = [
    ("Evgeniy", "uses_for_coding", "Claude Code", "2025-01-01"),
    ("Evgeniy", "uses_for_coding", "GitNexus", "2025-02-01"),
    ("Evgeniy", "uses_for_coding", "Codex CLI", "2025-03-01"),
    ("Evgeniy", "uses_for_coding", "Gemini CLI", "2025-04-01"),
    ("Evgeniy", "uses_for_coding", "GLM-4", "2025-05-01"),
    ("Evgeniy", "uses_for_coding", "MiniMax", "2025-06-01"),
    ("Evgeniy", "uses_for_coding", "Cursor", "2025-07-01"),
    ("Evgeniy", "lives_in", "Kyiv", "2020-01-01"),
    ("Evgeniy", "born_in", "Ukraine", "1990-01-01"),
    ("Evgeniy", "drinks", "espresso", "2015-01-01"),
    ("Evgeniy", "speaks", "Russian", "1992-01-01"),
    ("Evgeniy", "speaks", "Ukrainian", "1992-01-01"),
    ("Evgeniy", "speaks", "English", "2005-01-01"),
    ("Evgeniy", "owns_pet", "cat", "2018-01-01"),
    ("Evgeniy", "favorite_sport", "judo", "2010-01-01"),
    ("Evgeniy", "listens_to", "trance", "2008-01-01"),
    ("Alice", "uses_for_coding", "VSCode", "2024-01-01"),
    ("Alice", "uses_for_coding", "Copilot", "2024-02-01"),
    ("Bob", "uses_for_coding", "Vim", "2010-01-01"),
    ("Bob", "uses_for_coding", "tmux", "2011-01-01"),
    ("Charlie", "uses_for_coding", "Emacs", "2009-01-01"),
    ("Charlie", "uses_for_coding", "org-mode", "2012-01-01"),
    ("Dana", "uses_for_coding", "PyCharm", "2020-01-01"),
    ("Eve", "uses_for_coding", "JetBrains IDEA", "2019-01-01"),
    ("Frank", "uses_for_coding", "Sublime", "2014-01-01"),
    ("Gina", "uses_for_coding", "Atom", "2016-01-01"),
    ("Sun", "is_a", "star", "1900-01-01"),
    ("Moon", "orbits", "Earth", "1900-01-01"),
    ("Mars", "is_a", "planet", "1900-01-01"),
    ("Pluto", "reclassified_as", "dwarf planet", "2006-08-24"),
    ("Python", "is_a", "programming language", "1991-01-01"),
    ("Go", "is_a", "programming language", "2009-01-01"),
    ("Rust", "is_a", "programming language", "2010-01-01"),
    ("Kafka", "is_a", "message broker", "2011-01-01"),
    ("Redis", "is_a", "key-value store", "2009-01-01"),
    ("Postgres", "is_a", "relational database", "1996-01-01"),
    ("Mongo", "is_a", "document database", "2009-01-01"),
    ("React", "is_a", "frontend framework", "2013-01-01"),
    ("Vue", "is_a", "frontend framework", "2014-01-01"),
    ("Svelte", "is_a", "frontend framework", "2016-01-01"),
    ("Comfy", "is_a", "retail company", "2005-01-01"),
    ("Anthropic", "is_a", "AI lab", "2021-01-01"),
    ("OpenAI", "is_a", "AI lab", "2015-01-01"),
    ("Google", "is_a", "tech company", "1998-01-01"),
    ("Banana", "is_a", "fruit", "2000-01-01"),
    ("Apple", "is_a", "fruit", "2000-01-01"),
    ("Carrot", "is_a", "vegetable", "2000-01-01"),
    ("Beethoven", "composed", "9th symphony", "1824-05-07"),
    ("Mozart", "composed", "Requiem", "1791-12-05"),
    ("Eiffel Tower", "is_in", "Paris", "1889-03-31"),
]

assert len(FACTS) == 50, len(FACTS)


def main() -> None:
    root = Path(__file__).resolve().parent
    facts_dir = root / "memory" / "facts"
    facts_dir.mkdir(parents=True, exist_ok=True)
    ranked_for_query: list[str] = []
    for i, (s, p, o, vf) in enumerate(FACTS):
        fid = f"fact_{i:03d}"
        payload = {
            "id": fid,
            "subject": s,
            "predicate": p,
            "object": o,
            "valid_from": vf,
            "valid_until": "ongoing",
        }
        (facts_dir / f"{fid}.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if i < 7:
            ranked_for_query.append(fid)

    gt_path = root / "ground_truth_retrieval.json"
    gt_path.write_text(
        json.dumps(
            {
                "query": "what tools does Evgeniy use for coding",
                "results": [{"id": fid} for fid in ranked_for_query[:5]],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
