---
name: New config tier
about: Propose a new initial-config tier (ADR-008)
title: "[tier] "
labels: ["tier", "needs-triage"]
assignees: []
---

## Tier id

Proposed id (e.g., `T2_lite`, `T3_research`). Must be stable across releases.

## Base tier

Which existing tier does this extend (T0 / T1 / T2 / T3)?

## Deltas

What changes from the base tier?

- CLAUDE.md / CLAUDE.local.md:
- Skills added or removed:
- MCPs added, removed, or mock-vs-real:
- Vault state (snapshot id, expected files):

## Rationale

Why does this tier exist? What hypothesis about config-vs-capability does it test?

## Candidate tasks that benefit

Which existing or planned tasks would benefit from running on this tier?

- [ ] task or suite
- [ ] task or suite

## Trust tier compatibility

Can this tier's manifest be reproduced from a public sha256 chain? If not, mark trajectories produced here as `self_reported` only.
