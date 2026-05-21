# ab-sdk

Result-format library for agent-benchmarks. Reads and writes the canonical
run-directory layout used by `ab-cli` and `ab-server`:

```
results/<utc>-<run-id>/
  trajectory.jsonl    append-only event log (build spec §6)
  scores.json         scorer verdicts + totals
  metadata.yaml       model, tier, dataset_version, run_id, task_id
```

## Public API

```python
from ab_sdk import write_run_dir, read_run_dir, validate, RunDir
```

- `write_run_dir(run_dir, trajectory, metadata)` — serialise a `Trajectory`
  (from `ab_datasets.schemas`) plus a metadata dict into the three files.
- `read_run_dir(run_dir) -> RunDir` — parse `metadata.yaml` and return a
  `RunDir` model. Trajectory is loaded lazily via `read_trajectory(run_dir)`.
- `validate(run_dir) -> list[str]` — return a list of issues; empty list
  means the run dir conforms to the protocol.

See the workspace build spec §3 and §6 for the full contract.
