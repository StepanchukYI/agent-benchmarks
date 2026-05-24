"""Lever C — harden IFBench + faithfulness tasks (pure-prompt, no fixtures).

6 tasks:
  L0_405 — override default formatting (5-constraint Python output)
  L0_407 — negative-constraint chain (3-axis: word count + forbidden + mandatory)
  L0_501 — abstain chain (5 questions, classify ABSTAIN/ANSWER → 5-bit chain)
  L0_503 — contradiction chain (5 question/source sets → 5-bit chain)
  L0_505 — verbatim vs paraphrase (5 classifications → 5-letter VP chain)
  L0_510 — stale-fact (5 dated claims, classify STALE/STILL → 5-bit chain)
"""
import hashlib


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


# L0_501 — abstain chain
# 5 questions vs source "Q2-2025 quarterly report" (text embedded in YAML).
# Each question: 1 = should ABSTAIN (info not in source), 0 = ANSWERABLE.
# Hand-designed below.
def L0_501():
    classifications = [0, 1, 0, 1, 1]  # 5-bit
    chain = "".join(str(c) for c in classifications)
    return {"chain": chain, "digest": _sha1(chain)}


# L0_503 — contradiction chain
# 5 questions over a 3-source corpus. Each source set may agree or disagree.
# 1 = sources disagree (model must report disagreement), 0 = agree.
def L0_503():
    classifications = [1, 0, 1, 1, 0]
    chain = "".join(str(c) for c in classifications)
    return {"chain": chain, "digest": _sha1(chain)}


# L0_505 — verbatim vs paraphrase
# 5 quoted spans. V = appears verbatim in source; P = paraphrased.
def L0_505():
    classifications = ["V", "P", "P", "V", "P"]
    chain = "".join(classifications)
    return {"chain": chain, "digest": _sha1(chain)}


# L0_510 — stale-fact
# 5 dated facts from a 2021 source, considered as of TODAY = 2026.
# 1 = STALE (no longer true), 0 = STILL TRUE.
def L0_510():
    classifications = [1, 0, 1, 0, 1]
    chain = "".join(str(c) for c in classifications)
    return {"chain": chain, "digest": _sha1(chain)}


if __name__ == "__main__":
    for tid, fn in [("L0_501", L0_501), ("L0_503", L0_503), ("L0_505", L0_505), ("L0_510", L0_510)]:
        r = fn()
        print(f"{tid}: chain={r['chain']!r}  digest={r['digest']}")
