# Fixtures TODO — Track B (tasks)

Status board for fixture assets the task YAMLs depend on. The harness
resolves `fixture_ref` lazily, so tasks ship before fixtures exist; this
file is the inventory.

Last updated by the Phase-1 pilot: 5 task layers, 9 task YAMLs, see
`packages/ab-datasets/ab_datasets/L*/`.

## Path convention

Two conventions are currently in use across shipped tasks. **They must
converge** before Phase 1 row-6 (end-to-end `ab run`) lands, otherwise
the dry-run resolver can't find fixtures consistently.

| Convention | Example | Used by |
|---|---|---|
| **With `fixtures/` prefix** | `fixtures/repos/L0_smoke/L0_001/` | L0_001..L0_005 |
| **Without prefix** (docs/adding-a-task.md style) | `vault_snapshots/T2_seed_small.tar.gz` | L1_001, L2_001, L3a_001, L4_001 |

`docs/adding-a-task.md` shows the **without-prefix** form. The CLI
implementation in `packages/ab-cli/ab_cli/commands/task.py:dry_run`
currently searches at `repo_root/<fixture_ref>` and
`packages/ab-datasets/<fixture_ref>`, but **not** at
`packages/ab-datasets/fixtures/<fixture_ref>`, so the
without-prefix paths resolve to `missing` even when the file is on disk.

**Action item**: pick one convention, update either the four L1-L4 task
YAMLs or the dry-run resolver. Defer the decision to a Track-A maintainer.

## Inventory

Fixtures available right now (created by Track A scaffolding):

| Path | Status | Used by |
|---|---|---|
| `packages/ab-datasets/fixtures/config_tiers/T0_vanilla/manifest.yaml` | present | all tasks at T0 |
| `packages/ab-datasets/fixtures/config_tiers/T1_minimal/{manifest.yaml,CLAUDE.md}` | present | T1 cross-tier runs |
| `packages/ab-datasets/fixtures/config_tiers/T2_personal/{manifest.yaml,CLAUDE.md}` | present | L1_001, L2_001, L3a_001 at T2 |
| `packages/ab-datasets/fixtures/config_tiers/T3_full/manifest.yaml` | partial (no CLAUDE.md, no CLAUDE.local.md) | L4_001 at T3 |
| `packages/ab-datasets/fixtures/vault_snapshots/T2_seed_small.tar.gz` | present (340 B) | L1_001, L2_001, L3a_001 |
| `packages/ab-datasets/fixtures/repos/L0_smoke/L0_001..L0_005/` | present | L0_001..L0_005 |

Fixtures still missing for the Phase-1 pilot:

| Path | Used by | Priority | Notes |
|---|---|---|---|
| `packages/ab-datasets/fixtures/repos/calc_v1.tar.gz` | L4_001 | P1 | Python pkg with failing `tests/test_calc.py::test_divide_by_zero` and buggy `calc/__init__.py` returning `inf`. |
| `packages/ab-datasets/fixtures/config_tiers/T3_full/CLAUDE.md` | L4_001 | P1 | Anonymized maintainer CLAUDE.md. |
| `packages/ab-datasets/fixtures/config_tiers/T3_full/CLAUDE.local.md` | L4_001 | P1 | Anonymized CLAUDE.local.md with `vault_hub:` line. |
| `packages/ab-datasets/fixtures/vault_snapshots/T2_seed_small.tar.gz` content audit | L1_001, L3a_001 | P2 | Currently 340 B — verify it actually contains `Projects/agent-benchmarks/{hub.md, decisions.md, lessons.md}` and `.claude/CLAUDE.local.md` referenced by L3a_001. |
| `packages/ab-datasets/fixtures/mcp_mocks/obsidian-memory/*` | L1_001, L2_001, L3a_001 | P1 | Mock MCP server fixture so verified-tier rescoring is possible (LSN-007). |

## SHA256 manifest

Each fixture must have a `Fixture` entry in a manifest (path, sha256,
size) per `docs/adding-a-task.md` §3. The minimal-config-tier manifests
already encode SHA pinning (see T2_personal/manifest.yaml). Repo and vault
fixtures need an aggregate manifest written under
`packages/ab-datasets/fixtures/manifest.yaml` once paths are finalized.

## Privacy

Every fixture **must** pass `python scripts/privacy_scan.py` (or the
in-trajectory `privacy_check` scorer) against `docs/privacy-patterns.yaml`
before being committed. The patterns currently flag:

- real email addresses,
- maintainer home path,
- cloud/SaaS tokens (AWS, Slack, GitHub PAT, OpenAI sk-, PEM headers),
- `vault_hub:` leakage outside `.claude/`.

Anonymize before commit; never assume scrubbing happens later.
