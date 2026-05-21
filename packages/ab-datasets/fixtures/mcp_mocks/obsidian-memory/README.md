# obsidian-memory mock MCP server

Mock MCP server for memory-layer benchmark tasks (L0_606 + L1 memory
suite + L3a Obsidian adapter).

## What it simulates

- `search_vault` — substring search over the per-run vault snapshot.
- `read_vault_file` — read a markdown file by relative path.
- `read_hub` — read top-level or project `hub.md`.
- `append_decision` — write a structured decision entry to
  `decisions.md` (frontmatter validated against the schema).
- `append_lesson` — write a lesson to `lessons.md`.

## Why a mock

Real `obsidian-memory` writes against the operator's actual vault.
That's:

- Non-deterministic (write timestamps, vault drift between runs).
- Non-replayable (verified trust tier requires the rescore to derive
  the same result purely from the trajectory).
- A privacy risk (operator vault contains personal notes).

The mock seeds an isolated vault snapshot per run, simulates writes
in-memory, and emits deterministic tool returns. Same input → same
output → same verdict on rescore.

## Layout

```
mcp_mocks/obsidian-memory/
├── README.md              # this file
├── server.json            # MCP server descriptor + tool schemas
└── canned_responses.json  # optional fixed responses indexed by
                           # sha256(tool_name + canonical_json(args))
```

## Wiring

Task YAMLs reference the mock via:

```yaml
config:
  requires:
    mcps:
      - "obsidian-memory"
```

The tier manifest declares:

```yaml
mcps:
  - id: obsidian-memory
    config: { mock: true }
```

At run time the harness materializer copies `server.json` +
`canned_responses.json` into `<workdir>/.claude/mcps/obsidian-memory/`
and the agent talks to the mock via stdio.

## What lives in the per-run vault snapshot

Tier `T2_personal` ships a small seed (`T2_seed_small.tar.gz`); tier
`T3_full` ships a fuller seed (`T3_seed_full.tar.gz`). Both seeds are
anonymized — `<operator>` / `<example-project>` placeholders, no real
emails, paths, or handles.

## Replay determinism

The mock writes to an in-memory vault that lives for the duration of
the run. The trajectory captures every tool call + return. The
rescoring engine replays the trajectory; tool returns come straight
from the recorded events, not from re-executing the mock. The mock
only matters during the LIVE run.

## Implementation note

Python module `ab_harness.mcp_mocks.obsidian_memory` (not shipped in
this PR — wired in a follow-up). The descriptor + canned responses
are static so task authors can iterate on the contract without code.
