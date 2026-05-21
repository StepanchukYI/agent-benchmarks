# Fixtures TODO

Status board for fixture assets the task YAMLs depend on. The harness
resolves `fixture_ref` lazily, so tasks ship before fixtures exist;
this file is the inventory.

**Last updated**: after L0 close-out (39 tasks, 22 L0_smoke fixtures,
1 vault snapshot, 4 tier manifests). For per-task discrimination, see
`docs/L0-inventory.md`. For SHA pinning, see
`packages/ab-datasets/fixtures/manifest.yaml`.

## Path convention

`fixture_ref` is **always** prefixed with `fixtures/`, resolved
relative to `packages/ab-datasets/`. Two repo tests enforce this:

- `tests/test_l0_fixtures_resolve.py` — every declared `fixture_ref`
  exists on disk.
- `tests/test_l0_taxonomy.py` — L0 fixtures live under canonical
  roots (`fixtures/{repos,vault_snapshots,mcp_mocks,config_tiers}/`).

## Present (manifest.yaml authoritative)

| Root | Count | Notes |
|---|---|---|
| `fixtures/config_tiers/T0_vanilla/manifest.yaml` | 1 | empty CLAUDE.md by design |
| `fixtures/config_tiers/T1_minimal/{manifest,CLAUDE.md}` | 2 files | short generic CLAUDE.md |
| `fixtures/config_tiers/T2_personal/{manifest,CLAUDE.md}` | 2 files | with memory:memory-{session,write} skills + obsidian-memory mock |
| `fixtures/config_tiers/T3_full/manifest.yaml` | 1 | **missing CLAUDE.md and CLAUDE.local.md** (see below) |
| `fixtures/vault_snapshots/T2_seed_small.tar.gz` | 340 B | content audit recommended |
| `fixtures/repos/L0_smoke/L0_{001..010, 101..103, 201..202, 301..308, 501..505, 601..608}` | 22 dirs (L0 covers 39 tasks, 17 are text-only) | see manifest.yaml for SHA + size |

## Open / P1 — needed for L0 to be **truly end-to-end runnable**

The remaining items are L0-blocking for full cross-tier comparison
once Track A wires runners against real models. They are NOT blocking
Track B authoring.

| Path | Used by | Priority | Notes |
|---|---|---|---|
| `fixtures/config_tiers/T3_full/CLAUDE.md` | L0_601, 603, 604, 606, 607 (T3 leg) | P1 | Anonymized maintainer CLAUDE.md with full rule set. |
| `fixtures/config_tiers/T3_full/CLAUDE.local.md` | L0_601 (`also_run_on: T3`) | P1 | Must contain `vault_hub:` line for downstream L3a probes. |
| `T2_seed_small.tar.gz` content audit | L0_606 + later L1 | P1 | 340 B is suspiciously small; verify it contains `Projects/<active-project>/{hub,decisions,lessons}.md` actually used by L0_606's `requires.vault_state.has_decisions_md`. |
| `fixtures/mcp_mocks/obsidian-memory/` | L0_606 + L1 + L3a | P1 | Mock MCP server so verified-tier rescoring is possible (LSN-007). |

## Open / P2 — needed for L1+

| Path | Used by | Priority |
|---|---|---|
| `fixtures/repos/calc_v1.tar.gz` | L4_001 | P2 |
| `fixtures/vault_snapshots/T3_seed_medium.tar.gz` | L4 composite at T3 | P2 |
| `fixtures/mcp_mocks/lantern/` | L3b (10 tasks) | P2 |
| `fixtures/mcp_mocks/gitnexus/` | L3d.i (5 tasks) | P3 |
| `fixtures/mcp_mocks/graphify/` | L3d.ii (5 tasks) | P3 |
| `fixtures/mcp_mocks/backstage/` | L3c (deferred per build spec §5) | P3 |

## Privacy

`docs/privacy-patterns.yaml` defines the regex set the
`privacy_check` scorer enforces. As of L0 close-out, all 35 readable
fixture files scan clean (zero hits). Add new fixtures via:

```bash
uv run python scripts/privacy_scan.py packages/ab-datasets/fixtures
```

before committing. CI runs the same scan on every PR.

## Manifest

`packages/ab-datasets/fixtures/manifest.yaml` lists every fixture
with SHA256, size, kind, and visibility. Regenerate after any
fixture change with the helper script Track A is shipping
(`scripts/build_fixtures_manifest.py`, P1 deliverable). Until that
script lands, regenerate manually — there is a one-shot generator at
the bottom of `docs/L0-inventory.md` git log if you need the recipe.
