# Friend onboarding — share your benchmark runs

Goal: your runs show up on the public leaderboard next to mine, with the
same scoring + same `verified` trust tier when re-runnable.

You will:

1. Sign in with GitHub on the leaderboard.
2. Give the server **read** access to ONE GitHub repo where you'll commit
   your runs.
3. Run `ab` locally, push results to that repo, hit "Sync" — your rows
   appear within ~1 minute.

The server never gets write access to your repo. It clones over HTTPS,
re-scores from your trajectory, and stores the verdict in its own DB.

## Prerequisites

- Python 3.11+
- GitHub account
- A GitHub repo you own (empty is fine) — this is where your runs land.
  Convention: `github.com/<you>/agent-benchmarks-runs`.

## 1. Install the CLI

```bash
git clone https://github.com/StepanchukYI/agent-benchmarks.git
cd agent-benchmarks
uv pip install -e packages/ab-cli -e packages/ab-harness -e packages/ab-datasets -e packages/ab-sdk
ab --help
```

A `pip install ab-cli` path is planned; for now the CLI ships from the
monorepo source.

## 2. Sign in on the leaderboard

Open `https://bench.<host>/settings` → **Account** → **Sign in with
GitHub**. The page runs GitHub's device flow:

- it shows you a short code
- opens `https://github.com/login/device` in a new tab
- you paste the code, click Authorize
- the tab closes and the leaderboard shows your handle

No browser callback is involved. Server only ever sees a session token
scoped to `read:user` + `public_repo`.

## 3. Connect your runs repo

Two paths, pick one:

**A. Browser** — Settings → **Connected repos** → **Add repo** → paste
`https://github.com/<you>/agent-benchmarks-runs` → Connect.

**B. CLI** —

```bash
ab register https://github.com/<you>/agent-benchmarks-runs
```

The CLI walks the same device flow as the browser and stores the token
under `~/.config/agent-benchmarks/`.

## 4. Run + publish

```bash
# Run L0_smoke against Claude Sonnet (uses your ANTHROPIC_API_KEY).
ab run --suite L0_smoke --runner claude-code --model claude-sonnet-4-5 --tier T0

# Or against any Anthropic-compat vendor via the claude CLI:
ab run --suite L0_smoke --runner claude-code --model GLM-5.1 --tier T0 \
  --vendor zhipu --env ANTHROPIC_AUTH_TOKEN=$GLM_API_KEY

# Privacy-scrub before pushing (default patterns in docs/privacy-patterns.yaml).
python scripts/privacy_scrub.py ~/.ab/results

# Push to your runs repo.
cd /path/to/agent-benchmarks-runs
cp -r ~/.ab/results/* ab/runs/
git add ab/runs/ && git commit -m "L0 batch" && git push
```

## 5. Sync

Either click **Sync** next to the repo in Settings, or wait for the
server's fetcher poller (default: every 30s).

The server clones your repo into its cache, validates each run dir
against the schema, re-runs the deterministic scorer chain from your
trajectory, and inserts task_results into its DB. Your row joins the
leaderboard immediately after.

## Troubleshooting

- `401 Unauthorized` from Settings → token expired, re-sign in.
- Repo `status=failed` → tooltip shows the parse/scorer error; usually
  malformed `trajectory.jsonl` or missing `metadata.yaml`.
- Need to disconnect a repo → trash icon in Settings; the server stops
  fetching it but keeps already-ingested task_results (so your rows
  don't disappear retroactively).

## What the server reads vs stores

Reads (per sync) from your repo:

- `ab/runs/<utc>-<runid>/scores.json`
- `ab/runs/<utc>-<runid>/trajectory.jsonl`
- `ab/runs/<utc>-<runid>/metadata.yaml`

Stores in its own DB:

- The re-scored verdict + total + delta from your self-reported scores.
- A `trajectory_blob_ref` pointing back at your repo's commit + path
  (the viewer reads lazily under size + scrub caps).

Never stored:

- Workdir contents, env vars, API keys, anything outside `ab/runs/`.
