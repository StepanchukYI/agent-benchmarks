"""Harden L0 file-ops tasks per blueprint Family 1.

Per task: 6-8 input files including 1-2 traps (malformed / decoy);
multi-step pipeline (discover → filter → transform → fingerprint);
file_unchanged invariants on source files.

Tasks covered: L0_005, L0_007, L0_011, L0_022.
(L0_006 left for later — append-only edit needs different shape.)
"""
from __future__ import annotations

import hashlib
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "packages/ab-datasets/fixtures/repos/L0_smoke"
L0_DIR = REPO / "packages/ab-datasets/ab_datasets/L0_foundation"


# ============================================================
# L0_005: 6 modules + BROKEN.py + sha1 fingerprint
# ============================================================

L0_005_MODULES = {
    "auth.py": textwrap.dedent('''
        """Authentication module."""

        def login(username: str, password: str) -> bool:
            """Authenticate a user with username/password."""
            return True

        def logout(session_id: str) -> None:
            """Invalidate a session."""
            pass

        def refresh_token(token: str) -> str:
            """Refresh an expired JWT."""
            return "new_token"

        # @deprecated: use login() with explicit credentials
        def renew_session(session_id: str) -> bool:
            return True

        def _hash_password(pw: str) -> str:
            return "hash"
    ''').lstrip(),
    "billing.py": textwrap.dedent('''
        """Billing module."""

        def charge(account: str, amount: float) -> str:
            """Charge an account; returns transaction id."""
            return "txn-1"

        def refund_full(transaction_id: str) -> bool:
            """Refund the full amount of a transaction."""
            return True

        # @deprecated: use refund_full or refund_partial
        def reimburse(account: str, amount: float) -> str:
            return "txn-r"

        def _audit_log(event: dict) -> None:
            pass
    ''').lstrip(),
    "cache.py": textwrap.dedent('''
        """In-memory cache."""

        def get(key: str):
            return None

        def set(key: str, value) -> None:
            pass

        def delete(key: str) -> bool:
            return True

        def invalidate(prefix: str) -> int:
            return 0

        # @deprecated: use invalidate(prefix="")
        def flush() -> None:
            pass
    ''').lstrip(),
    "metrics.py": textwrap.dedent('''
        """Metrics collection."""

        def record(name: str, value: float) -> None:
            pass

        def snapshot() -> dict:
            return {}

        def _internal_tick() -> None:
            pass
    ''').lstrip(),
    "storage.py": textwrap.dedent('''
        """Object storage."""

        def put(bucket: str, key: str, blob: bytes) -> str:
            return "etag"

        def get(bucket: str, key: str) -> bytes:
            return b""

        def delete(bucket: str, key: str) -> bool:
            return True

        def _validate_bucket(b: str) -> bool:
            return True
    ''').lstrip(),
    "worker.py": textwrap.dedent('''
        """Background worker queue."""

        def enqueue(task: dict) -> str:
            return "job-1"

        def status(job_id: str) -> str:
            return "pending"

        # @deprecated: use enqueue() in a loop
        def batch_enqueue(tasks: list) -> list:
            return []

        def _retry(job_id: str) -> bool:
            return True
    ''').lstrip(),
}

# Stable API (alphabetical modules, alphabetical functions within each)
L0_005_STABLE = {
    "auth": ["login", "logout", "refresh_token"],
    "billing": ["charge", "refund_full"],
    "cache": ["delete", "get", "invalidate", "set"],
    "metrics": ["record", "snapshot"],
    "storage": ["delete", "get", "put"],
    "worker": ["enqueue", "status"],
}


def harden_L0_005() -> None:
    d = FIXTURES / "L0_005"
    d.mkdir(parents=True, exist_ok=True)

    # Wipe existing .py files
    for old in d.glob("*.py"):
        old.unlink()
    if (d / "BROKEN.py").exists():
        (d / "BROKEN.py").unlink()

    # Write 6 modules
    for name, text in L0_005_MODULES.items():
        (d / name).write_text(text, encoding="utf-8")

    # Write BROKEN.py with UTF-16 BOM + binary noise
    broken = b"\xff\xfe" + b"def " + bytes([0x00, 0xff, 0xfe, 0x80]) + b"garbage\n"
    (d / "BROKEN.py").write_bytes(broken)

    # Compute expected API.md
    api_md = ""
    for mod in sorted(L0_005_STABLE):
        api_md += f"## {mod}\n"
        for fn in sorted(L0_005_STABLE[mod]):
            api_md += f"- {fn}\n"
        api_md += "\n"
    api_md = api_md.rstrip("\n") + "\n"
    sha1 = hashlib.sha1(api_md.encode()).hexdigest()

    yaml = f"""id: L0_005
layer: L0
suite: extract
title: "Extract stable API across 6 modules + skip malformed + sha1 fingerprint"
description: |
  Fixture: 7 files in the workdir.

      auth.py, billing.py, cache.py, metrics.py, storage.py, worker.py
        — six valid Python modules.
      BROKEN.py
        — NOT a valid Python source (UTF-16 BOM + binary noise at byte 4).
          Reading it as UTF-8 will throw UnicodeDecodeError. The agent
          must DETECT this and SKIP — not crash, not include any
          fabricated content from it.

  STEP 1 — Discover.
    List the fixture directory. There are exactly 7 `.py` files.

  STEP 2 — Skip BROKEN.py.
    Attempt to read each `.py`. `BROKEN.py` will fail UTF-8 decode —
    handle the error gracefully and exclude it from further analysis.

  STEP 3 — Extract stable API.
    For each of the six valid modules, list every top-level function
    that is:
      - public (name does NOT start with `_`), AND
      - NOT deprecated (no `# @deprecated:` comment on the line
        IMMEDIATELY above the `def`).

    Deprecated functions present in the fixture (must be EXCLUDED):
      auth.renew_session, billing.reimburse, cache.flush,
      worker.batch_enqueue.
    Private functions present (must be EXCLUDED):
      auth._hash_password, billing._audit_log, metrics._internal_tick,
      storage._validate_bucket, worker._retry.

  STEP 4 — Sort and structure.
    Sort module names alphabetically. Within each module, sort function
    names alphabetically. Write the result to `API.md` with this EXACT
    format (one blank line between module sections, single trailing
    newline at EOF):

        ## auth
        - login
        - logout
        - refresh_token

        ## billing
        - charge
        - refund_full

        ...

  STEP 5 — Fingerprint.
    Compute the lowercase hex SHA-1 of the UTF-8 bytes of `API.md`.
    Write the 40-char digest as the SOLE content of `checksum.txt`
    (no trailing newline, no prefix).

  STEP 6 — Invariant.
    Do NOT modify any source file. `BROKEN.py` and the six valid
    modules must remain byte-identical to the fixture seed.

  Failure modes:
    - including a deprecated or private function in `API.md`,
    - including content from `BROKEN.py` (or crashing on its read),
    - wrong module / function sort order,
    - wrong sha1 in `checksum.txt` (anything other than the digest of
      the byte-exact `API.md`),
    - modifying any source file.

fixture_ref: "fixtures/repos/L0_smoke/L0_005/"

config:
  required_tier: T0
  recommended_tier: T0
  also_run_on: [T2]
  requires: {{skills: [], mcps: [], vault_state: {{}}}}

scorer_chain:
  - name: file_diff_and_invariants
    kind: deterministic
    config:
      assertions:
        - kind: workdir_file_content_equals
          path: "API.md"
          content: |
            ## auth
            - login
            - logout
            - refresh_token

            ## billing
            - charge
            - refund_full

            ## cache
            - delete
            - get
            - invalidate
            - set

            ## metrics
            - record
            - snapshot

            ## storage
            - delete
            - get
            - put

            ## worker
            - enqueue
            - status
        - kind: workdir_file_content_equals
          path: "checksum.txt"
          content: "{sha1}"
        - kind: file_unchanged
          path: "auth.py"
        - kind: file_unchanged
          path: "billing.py"
        - kind: file_unchanged
          path: "cache.py"
        - kind: file_unchanged
          path: "metrics.py"
        - kind: file_unchanged
          path: "storage.py"
        - kind: file_unchanged
          path: "worker.py"
        - kind: file_unchanged
          path: "BROKEN.py"

  - name: privacy_check
    kind: privacy_check
    config: {{patterns_path: "docs/privacy-patterns.yaml"}}

  - name: tool_skill
    kind: deterministic
    config: {{max_tool_calls: 12, pass_threshold: 0.8}}

  - name: context_efficiency
    kind: deterministic
    config: {{target_tokens: 3000, max_tokens: 8000, pass_threshold: 0.6}}

  - name: latency_cost
    kind: deterministic
    config: {{target_ms: 30000, max_ms: 90000, pass_threshold: 0.6}}

acceptance_criteria:
  - "API.md has 6 sections in alphabetical order with alphabetical functions."
  - "checksum.txt holds the sha1 of API.md byte-content."
  - "All 7 source files unchanged."
  - "Privacy scan zero hits."

weights:
  correctness: 0.70
  tool_skill: 0.10
  context_efficiency: 0.10
  latency_cost: 0.05
  memory_specific: 0.05

difficulty: hard
visibility: public
trust_tier_ceiling: verified

tags:
  - L0
  - extract
  - file-ops
  - multi-file
  - decoy
  - state-chain
  - hash
  - deterministic
  - byte-exact-output
  - output-normalization-sensitive
  - reasoning-sensitive
"""
    (L0_DIR / "L0_005-multi-file-api-extract-with-deprecation.yaml").write_text(yaml, encoding="utf-8")
    print(f"  L0_005: 7 modules (1 BROKEN), API.md sha1={sha1[:16]}…")


# ============================================================
# L0_022: chained sha256 over 5 files
# ============================================================

def harden_L0_022() -> None:
    d = FIXTURES / "L0_022"
    d.mkdir(parents=True, exist_ok=True)

    # Wipe existing
    for old in d.iterdir():
        if old.is_file():
            old.unlink()

    # Deterministic 5 files with distinct seeded byte content
    files = {}
    for i, name in enumerate(["alpha.bin", "bravo.bin", "charlie.bin", "delta.bin", "echo.bin"]):
        # 1 KB of seeded pseudo-random bytes
        seed = hashlib.sha256(f"L0_022:{name}".encode()).digest()
        content = (seed * 32)[:1024]
        (d / name).write_bytes(content)
        files[name] = content

    # Decoy: one .bak file that should be IGNORED by the model
    decoy = b"DECOY: do not include in fingerprint chain.\n" * 30
    (d / "alpha.bin.bak").write_bytes(decoy)

    # Compute expected
    digests = []
    for name in ["alpha.bin", "bravo.bin", "charlie.bin", "delta.bin", "echo.bin"]:
        digests.append(hashlib.sha256(files[name]).hexdigest())
    chain = "|".join(digests)
    meta_sha = hashlib.sha256(chain.encode()).hexdigest()

    yaml = f"""id: L0_022
layer: L0
suite: exec
title: "Multi-file sha256 chain → meta-fingerprint (5 files + 1 decoy)"
description: |
  Fixture: 6 files in the workdir.

      alpha.bin, bravo.bin, charlie.bin, delta.bin, echo.bin
        — 5 deterministic 1 KB binaries that ARE part of the chain.
      alpha.bin.bak
        — a decoy backup file. MUST be excluded from the chain.

  STEP 1 — Per-file digests.
    Compute the lowercase hex SHA-256 of the bytes of each of the
    five CHAIN files (NOT the .bak decoy). Use shell `shasum -a 256`
    or Python `hashlib.sha256(open(p, 'rb').read()).hexdigest()`.

  STEP 2 — Order + join.
    Order the digests in the canonical file order:
      alpha.bin → bravo.bin → charlie.bin → delta.bin → echo.bin
    Pipe-join the 5 digests with the literal `|` separator (no spaces).

  STEP 3 — Meta-fingerprint.
    Compute the SHA-256 of the UTF-8 bytes of the joined string (no
    trailing newline). Output ONLY the 64-character lowercase hex
    digest as the SOLE final assistant message. No prefix, no quotes,
    no markdown, no trailing newline.

  STEP 4 — Invariant.
    Do NOT modify or create any file. All 6 fixture files must
    remain byte-identical.

  You MUST actually compute the chain — the meta-digest is NOT in this
  description.

  Failure modes:
    - including alpha.bin.bak in the chain (gives a different digest),
    - wrong order (e.g. alphabetical → identical here but different
      casing would diverge),
    - wrong separator (`,` or space instead of `|`),
    - using SHA-1 instead of SHA-256,
    - emitting any intermediate digest in the final message.

fixture_ref: "fixtures/repos/L0_smoke/L0_022/"

config:
  required_tier: T0
  recommended_tier: T0
  also_run_on: [T2]
  requires: {{skills: [], mcps: [], vault_state: {{}}}}

scorer_chain:
  - name: range_then_hash
    kind: deterministic
    config:
      assertions:
        - kind: final_assistant_message_equals
          expected: "{meta_sha}"
          trim_whitespace: true
        - kind: final_assistant_message_does_not_contain
          forbidden:
            - "|"
            - "alpha"
            - "bravo"
        - kind: file_unchanged
          path: "alpha.bin"
        - kind: file_unchanged
          path: "bravo.bin"
        - kind: file_unchanged
          path: "charlie.bin"
        - kind: file_unchanged
          path: "delta.bin"
        - kind: file_unchanged
          path: "echo.bin"
        - kind: file_unchanged
          path: "alpha.bin.bak"

  - name: privacy_check
    kind: privacy_check
    config: {{patterns_path: "docs/privacy-patterns.yaml"}}

  - name: tool_skill
    kind: deterministic
    config: {{max_tool_calls: 8, pass_threshold: 0.8}}

  - name: context_efficiency
    kind: deterministic
    config: {{target_tokens: 2500, max_tokens: 6000, pass_threshold: 0.6}}

  - name: latency_cost
    kind: deterministic
    config: {{target_ms: 25000, max_ms: 60000, pass_threshold: 0.6}}

acceptance_criteria:
  - "Final message is the 64-char lowercase hex sha256 of the pipe-joined per-file sha256 digests."
  - "alpha.bin.bak is excluded from the chain."
  - "All 6 fixture files unchanged."
  - "Privacy scan zero hits."

weights:
  correctness: 0.70
  tool_skill: 0.10
  context_efficiency: 0.10
  latency_cost: 0.05
  memory_specific: 0.05

difficulty: hard
visibility: public
trust_tier_ceiling: verified

tags:
  - L0
  - exec
  - file-ops
  - multi-file
  - hash
  - chain
  - decoy
  - state-chain
  - deterministic
  - byte-exact-output
  - output-normalization-sensitive
  - reasoning-sensitive
"""
    (L0_DIR / "L0_022-exec-sha256-fingerprint.yaml").write_text(yaml, encoding="utf-8")
    print(f"  L0_022: 5+1 files, meta-sha256={meta_sha[:16]}…")


# ============================================================
# L0_011: 5-file rotation with sha1 verify + locked decoy
# ============================================================

def harden_L0_011() -> None:
    d = FIXTURES / "L0_011"
    d.mkdir(parents=True, exist_ok=True)

    # Wipe existing
    for old in d.iterdir():
        if old.is_file():
            old.unlink()

    # 5 files in a rotation chain: a → b → c → d → e → a
    # Each file holds its initial content; rotation = filename keeps but content shifts left
    initial = {
        "a.txt": "ALPHA content one — initial value A\n",
        "b.txt": "BRAVO content two — initial value B\n",
        "c.txt": "CHARLIE content three — initial value C\n",
        "d.txt": "DELTA content four — initial value D\n",
        "e.txt": "ECHO content five — initial value E\n",
    }
    for name, content in initial.items():
        (d / name).write_text(content, encoding="utf-8")

    # Decoy: locked.txt — read-only, must NOT be touched
    locked = "LOCKED: this file must remain byte-identical after rotation.\n"
    (d / "locked.txt").write_text(locked, encoding="utf-8")

    # Expected after one LEFT rotation:
    #   a.txt ← b's content, b.txt ← c, c.txt ← d, d.txt ← e, e.txt ← a
    after = {
        "a.txt": initial["b.txt"],
        "b.txt": initial["c.txt"],
        "c.txt": initial["d.txt"],
        "d.txt": initial["e.txt"],
        "e.txt": initial["a.txt"],
    }

    # sha1 of concatenation of post-rotation contents
    concat = "".join(after[k] for k in sorted(after))
    sha1 = hashlib.sha1(concat.encode()).hexdigest()

    yaml = f"""id: L0_011
layer: L0
suite: file-ops
title: "5-file LEFT rotation with sha1 verify + locked-file invariant"
description: |
  Fixture: 6 files in the workdir.

      a.txt, b.txt, c.txt, d.txt, e.txt — 5 files forming a rotation cycle.
      locked.txt — a decoy that MUST remain byte-identical (do NOT
                   read, write, or even touch it).

  Each of the 5 cycle files starts with content like:
      "ALPHA content one — initial value A\\n"

  STEP 1 — Perform LEFT rotation.
    Replace each file's content with the content of its NEXT neighbour
    in the cycle (a ← b, b ← c, c ← d, d ← e, e ← a).

    Concretely the new contents should be:
      a.txt → "BRAVO content two — initial value B\\n"
      b.txt → "CHARLIE content three — initial value C\\n"
      c.txt → "DELTA content four — initial value D\\n"
      d.txt → "ECHO content five — initial value E\\n"
      e.txt → "ALPHA content one — initial value A\\n"

    Constraint: no INTERMEDIATE files. Do NOT create `.tmp`, `.bak`,
    `.swp`, or any extra file. The rotation must be performed using
    only in-memory shuffling and the 5 final writes.

  STEP 2 — Verify.
    Compute the SHA-1 of the UTF-8 bytes of the concatenation of the
    5 post-rotation file contents, taken in the alphabetical order
    a, b, c, d, e (no separator between concatenations, single newline
    at the end of each file is preserved). Write the 40-char lowercase
    hex digest as the SOLE content of `rotation.sha1` (no trailing
    newline, no prefix).

  STEP 3 — Invariant.
    `locked.txt` must remain byte-identical to its seed. Do NOT read
    it, write it, or include its content in any computation.

  Failure modes:
    - touching locked.txt (any read or write),
    - creating an intermediate .tmp / .bak / .swp file,
    - off-by-one rotation (rotating right instead of left, or by 2),
    - writing the wrong sha1 to rotation.sha1,
    - leaving the rotation incomplete (e.g. a.txt still has "ALPHA"
      because the model overwrote it before reading b).

fixture_ref: "fixtures/repos/L0_smoke/L0_011/"

config:
  required_tier: T0
  recommended_tier: T0
  also_run_on: [T2]
  requires: {{skills: [], mcps: [], vault_state: {{}}}}

scorer_chain:
  - name: rotation_check
    kind: deterministic
    config:
      assertions:
        - kind: workdir_file_content_equals
          path: "a.txt"
          content: "BRAVO content two — initial value B\\n"
        - kind: workdir_file_content_equals
          path: "b.txt"
          content: "CHARLIE content three — initial value C\\n"
        - kind: workdir_file_content_equals
          path: "c.txt"
          content: "DELTA content four — initial value D\\n"
        - kind: workdir_file_content_equals
          path: "d.txt"
          content: "ECHO content five — initial value E\\n"
        - kind: workdir_file_content_equals
          path: "e.txt"
          content: "ALPHA content one — initial value A\\n"
        - kind: workdir_file_content_equals
          path: "rotation.sha1"
          content: "{sha1}"
        - kind: file_unchanged
          path: "locked.txt"
        - kind: workdir_file_absent
          path: "a.txt.tmp"
        - kind: workdir_file_absent
          path: "a.txt.bak"
        - kind: workdir_file_absent
          path: "rotation.tmp"

  - name: privacy_check
    kind: privacy_check
    config: {{patterns_path: "docs/privacy-patterns.yaml"}}

  - name: tool_skill
    kind: deterministic
    config: {{max_tool_calls: 14, pass_threshold: 0.8}}

  - name: context_efficiency
    kind: deterministic
    config: {{target_tokens: 3000, max_tokens: 7000, pass_threshold: 0.6}}

  - name: latency_cost
    kind: deterministic
    config: {{target_ms: 25000, max_ms: 60000, pass_threshold: 0.6}}

acceptance_criteria:
  - "All 5 cycle files have rotated content (LEFT rotation)."
  - "rotation.sha1 holds the sha1 of the concatenated post-rotation contents."
  - "locked.txt unchanged."
  - "No intermediate .tmp/.bak files left in workdir."
  - "Privacy scan zero hits."

weights:
  correctness: 0.70
  tool_skill: 0.15
  context_efficiency: 0.05
  latency_cost: 0.05
  memory_specific: 0.05

difficulty: hard
visibility: public
trust_tier_ceiling: verified

tags:
  - L0
  - file-ops
  - rotation
  - multi-file
  - locked-file-invariant
  - decoy
  - state-chain
  - hash
  - deterministic
  - byte-exact-output
  - output-normalization-sensitive
  - reasoning-sensitive
"""
    (L0_DIR / "L0_011-three-way-rename-rotate.yaml").write_text(yaml, encoding="utf-8")
    print(f"  L0_011: 5-cycle + locked.txt, rotation.sha1={sha1[:16]}…")


def main() -> int:
    harden_L0_005()
    harden_L0_022()
    harden_L0_011()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
