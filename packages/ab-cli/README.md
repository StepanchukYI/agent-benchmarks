# ab-cli

Operator-facing CLI for agent-benchmarks. Built on Typer + Rich.

Phase 0 ships subcommand stubs that print the planned scope. Real
implementations land in Phase 1 (build spec §5).

## Usage

```
ab --help
ab --version

ab register <repo-url> [--default-branch main]
ab run --suite L0_smoke --model claude-sonnet [--tier T0] [--tiers T0,T2]
ab publish [--message "update results"]
ab replay <run-id> <commit-sha>
ab submit [--server https://leaderboard.example.com]
ab evolve [--generation 1]
```

## Status

| Command  | Phase 1 row | Notes |
|----------|-------------|-------|
| register | 7           | GitHub OAuth device flow + repo registration |
| run      | 6           | end-to-end harness execution                 |
| publish  | 7           | git add + commit + push wrapper              |
| replay   | —           | replay a remote commit                        |
| submit   | —           | legacy push submission, kept for P1 fallback |
| evolve   | Phase 7     | L5 auto-evolution loop                       |

See the workspace build spec §3 and §4 P0.9 for the full contract.
