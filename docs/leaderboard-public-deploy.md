# Leaderboard — public deploy for friends

How to stand up a public leaderboard on a dedicated server that shows
REAL benchmark results (your own runs), not fake seed data.

Reuses the production deploy stack (`infra/docker-compose.deploy.yml` +
the ghcr.io-hosted images built by `.github/workflows/build-images.yml`).

## One-shot pipeline

```bash
# 1. Run a real model × effort × task matrix on your local machine.
for m in claude-sonnet-4-5 claude-haiku-4-5 claude-opus-4-7; do
  for e in low medium high; do
    for t in L0_001 L0_002 L0_003 L0_004 L0_005 L0_101 L0_201 L0_402 L0_605; do
      ab run --suite L0_smoke --task "$t" \
        --runner claude-code --model "$m" --effort "$e" --tier T0 \
        --results-root ~/.ab/results
    done
  done
done

# 2. Privacy-scrub everything BEFORE shipping to a public host.
python scripts/privacy_scrub.py ~/.ab/results

# 3. Ingest into a LOCAL server DB to sanity-check the leaderboard.
DATABASE_URL=sqlite:///$(pwd)/packages/ab-server/ab.db \
python scripts/ingest_local_runs.py \
    --results-root ~/.ab/results \
    --repo-handle <your-github-handle> \
    --repo-url https://github.com/<you>/agent-benchmarks-runs \
    --visibility public

# 4. Boot the server locally, verify rows show up.
cd packages/ab-server && uv run uvicorn ab_server.main:app --port 8000
curl -s http://localhost:8000/api/v1/leaderboard | jq '.rows | length'

# 5. Ship the DB to the dedicated server.
scp packages/ab-server/ab.db <user>@<host>:/srv/agent-benchmarks/seed.db
```

## On the dedicated server (homelab or VPS)

```bash
# One-time bootstrap.
git clone --depth 1 https://github.com/StepanchukYI/agent-benchmarks.git
cd agent-benchmarks
cp infra/.env.example .env

# Required env (edit .env):
#   POSTGRES_PASSWORD=$(openssl rand -hex 16)
#   SESSION_SECRET=$(openssl rand -hex 32)
#   GITHUB_CLIENT_ID=<from github.com/settings/developers>
#   GITHUB_CLIENT_SECRET=<from github.com/settings/developers>
#   AB_DOMAIN=bench.example.com
#   AB_API_BASE_URL=https://bench.example.com/api/v1
#   ALLOWED_ORIGINS=https://bench.example.com
#   IMAGE_OWNER=stepanchukyi
#   IMAGE_TAG=main

# Bring up the stack from pre-built GHCR images.
docker compose -f infra/docker-compose.deploy.yml --env-file .env up -d

# Wait for Caddy to provision Let's Encrypt + the server to migrate.
docker compose -f infra/docker-compose.deploy.yml logs -f caddy

# Seed real bench data the first time.
# (Mount the seed.db from step 5 above, OR run ingest_local_runs.py inside
# the ab-server container against an attached results volume.)
docker compose -f infra/docker-compose.deploy.yml exec ab-server \
    python scripts/ingest_local_runs.py \
        --results-root /srv/results \
        --repo-handle <your-handle> \
        --repo-url <your-runs-repo> \
        --visibility public

# Visit https://bench.example.com — the leaderboard should now show
# rows per (model, tier) backed by your real ab run outputs.
```

## Daily refresh

```bash
# After running new benches locally:
python scripts/ingest_local_runs.py --results-root ~/.ab/results \
    --repo-handle <handle> --repo-url <url> --visibility public

# Idempotent — already-ingested runs (same run dir name) are skipped.
```

## What friends see

* `GET /api/v1/leaderboard` — per-model, per-tier per-pillar scores.
* `GET /api/v1/leaderboard?include_task_tags=reasoning-sensitive` —
  scores on the reasoning-sensitive subset only (axis 1 from
  `docs/result-sensitivity-axes.md`).
* `GET /api/v1/leaderboard?exclude_task_tags=factual-recall` — drop
  knowledge-cutoff-biased tasks.
* `GET /api/v1/tags` — the full sensitivity tag taxonomy for the FE
  picker.
* `GET /api/v1/submissions?operator=<handle>` — list-only of public
  submissions. Private submissions remain hidden by the
  is_public-must-be-true filter.

## Privacy invariants enforced at ingest

* `--no-privacy-gate` is dev-only. Default: every run dir is scanned
  against `docs/privacy-patterns.yaml` BEFORE insert. High-severity
  hits → ingest refused for that run.
* `--visibility public` flips `RegisteredRepo.is_public=True`. Drop
  to `private` if you don't want friends to see this batch yet.
* The trajectory file path is stored as `trajectory_blob_ref`. The
  trajectory viewer reads it lazily via the size-cap + scrub guards
  added in the May code-review pass.

## When NOT to use this

* You want to compare runs from MULTIPLE operators. Then use the
  GitHub OAuth + `ab register` + `ab publish` flow (each operator
  hosts their own results repo; the server fetches each).
* `ingest_local_runs.py` is the SHORTCUT for solo + small-team setups:
  one operator, many runs, one shared dashboard.

## Adding new (model, effort) combos

### Direct API runner (Anthropic-compat)

```bash
ab run --suite L0_smoke --task L0_001 \
       --runner anthropic-compat --model glm-4.6 --tier T0 \
       --base-url https://open.bigmodel.cn/api/anthropic \
       --api-key $GLM_API_KEY
```

Single-prompt completion only — no agentic tool-calling loop yet.

### Vendor-routed claude-code (RECOMMENDED for honest cross-vendor bench)

`claude` CLI itself supports `ANTHROPIC_BASE_URL` env. Run the SAME
scaffold (claude-code) against ANY Anthropic-compat vendor by setting
the env at subprocess level. ab run wraps this via `--vendor` +
`--env` flags so you don't have to fiddle with shell-rc wrappers:

```bash
# Zhipu GLM via claude-code scaffold:
ab run --suite L0_smoke --task L0_001 --tier T0 \
       --runner claude-code --model GLM-5.1 \
       --vendor zhipu \
       --env ANTHROPIC_AUTH_TOKEN=$GLM_API_KEY \
       --env CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

# MiniMax via claude-code scaffold:
ab run --suite L0_smoke --task L0_001 --tier T0 \
       --runner claude-code --model MiniMax-M2.7 \
       --vendor minimax \
       --env ANTHROPIC_AUTH_TOKEN=$MINIMAX_API_KEY \
       --env CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

# Same shape for Moonshot Kimi (--vendor moonshot) +
# DeepSeek (--vendor deepseek).
```

`--vendor <name>` resolves to the canonical base URL in
`ab_harness.models.VENDOR_BASE_URLS` (anthropic | zhipu | moonshot |
minimax | deepseek). You supply the auth token explicitly via --env
— ab never reads vendor-specific keys from the shell to keep the
privacy boundary clean.

### Local runner

```bash
ab run --runner local --model gemma3-27b --tier T0 --suite L0_smoke --task L0_001
# Uses http://localhost:11434/v1 (Ollama). LM Studio / vLLM /
# llama.cpp work via --base-url override.
```

### codex-cli / gemini-cli scaffolds

```bash
# OpenAI Codex via codex-cli (CLI must be installed):
ab run --runner codex-cli --model gpt-5.4 --effort low --tier T0 ...

# Google Gemini via gemini-cli (CLI must be installed):
ab run --runner gemini-cli --model gemini-3-pro --tier T0 ...
```

Then ingest → leaderboard picks up new rows automatically.
