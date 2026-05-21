# ab-datasets

Task catalog, fixtures, and Pydantic v2 schemas for the agent-benchmarks workspace.

This package owns:

- Pydantic models for `Task`, `Fixture`, `ScorerChain`, `Tier`, `TierManifest`, `Trajectory`, `Turn`, `ScorerVerdict`, `Submission`.
- YAML loaders for task definitions under `ab_datasets/L{0..5}_*/`.
- Reference fixtures for the four initial config tiers (T0..T3), vault snapshots, test repos, and MCP mocks.
- JSON Schema export entrypoint used by `make schema-export`.

See vault `Projects/agent-benchmarks/hub.md` and `docs/schemas/` for the canonical references and the latest generated schemas.
