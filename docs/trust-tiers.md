# Trust tiers

Trust tier is the second axis on every submission, alongside the score itself. It tells a reader how much weight to put on a result. The model is borrowed from the security-disclosure world: claims are useful, but verified claims are more useful, and first-party runs are the most useful.

There are three trust tiers. They are defined by ADR-007 and refined by LSN-005 and LSN-007.

## `self_reported`

The submitter ran the task locally, the scorers passed locally, and the trajectory was published to a contributor repo. The server has fetched the trajectory but has not (or cannot) re-score it.

Use case: any task where the scorer chain depends on state outside the trajectory file — e.g., a live MCP server, a network call, a non-deterministic LLM-judge with no recorded judge output. These results are accepted and surfaced, but flagged.

## `verified`

The server re-ran every deterministic scorer in the chain from the published `trajectory.jsonl` alone, and the re-scored numbers match the self-reported ones within tolerance. LLM-judge scorers are audited (the server inspects the recorded judge ensemble) but not re-executed.

For a task to be eligible:

- Every deterministic scorer must be re-runnable from the trajectory file alone (no external state, no live API).
- `Task.trust_tier_ceiling` must be `verified` or `official`.
- The trajectory must declare `privacy_check` and that scorer must have passed.

Discrepancy beyond tolerance demotes the submission to `self_reported` and records `discrepancy_pct` on the submission row.

## `official`

The server itself executed the run end-to-end. The trajectory was produced inside the server's own harness, with the server's pinned `ab-datasets` and `ab-harness` versions, on a tier whose manifest the server validated against its tier registry.

Use case: any benchmarking statement that needs to be reproducible by a third party with no assumption about the submitter's local environment.

## Per-layer ceilings

Some layers cap below the maximum trust tier because their scorers are inherently external.

| Layer | Maximum trust tier | Why |
|-------|--------------------|-----|
| L0 foundation | `official` | Pure file ops, deterministic. |
| L1 memory | `verified` | Vault state diff is captured in the trajectory; re-scorable. |
| L2 skills | `verified` | Single-skill tasks have deterministic scorers. |
| L3 domains | `verified` (mock) / `self_reported` (live) | When run against MCP mocks, fully re-scorable. Live runs depend on external services and ceiling drops. |
| L4 composite | `verified` | If all sub-scorers are deterministic; otherwise `self_reported`. |
| L5 evolved | `self_reported` | Evolved configs may include components the server cannot reproduce. |

A task's declared `trust_tier_ceiling` is the upper bound. The realized trust tier is the minimum of the declared ceiling and the actual re-score outcome.

## Re-scoring property

The system relies on one core property (LSN-007): given only `trajectory.jsonl`, the server can re-execute every deterministic scorer and obtain the same verdict the submitter obtained. Practically this means:

- Scorers consume the trajectory, not the live sandbox.
- Tool returns, vault state diffs, model outputs, and any reference data the scorer compares against must all be present in the file.
- Runners must record enough detail in `tool_returns` and `vault_state_diff` to drive every downstream check.

If a new scorer needs state that is not in the trajectory, either extend the trajectory schema to include that state (additive only, never remove fields) or downgrade the task's ceiling to `self_reported`.

## References

- ADR-007 — GitHub OAuth + pull-based aggregation
- LSN-005 — trust tiers as a first-class axis
- LSN-007 — deterministic re-scorability is the verifiability lever
