# ab-server

FastAPI backend for **agent-benchmarks**: hosts the leaderboard, ingests
submissions from registered repos (ADR-007 pull-based), re-scores trajectories,
and serves the `ab-leaderboard` SPA.

Phase 0 status: skeleton only. `/healthz` and `/api/v1/version` are live; every
other endpoint declared in the API contract (Build Spec §10) returns
`501 Not Implemented` with an explanatory JSON body.

## Run (dev)

```bash
uv sync
uvicorn ab_server.main:app --reload
```

Then visit:
- `http://localhost:8000/healthz`
- `http://localhost:8000/api/v1/version`
- `http://localhost:8000/docs` — OpenAPI / Swagger UI
- `http://localhost:8000/openapi.json`

## Config

Read from environment (`pydantic-settings`):

| Var | Default |
|-----|---------|
| `DATABASE_URL` | `sqlite:///./ab.db` |
| `GITHUB_CLIENT_ID` | _empty_ |
| `GITHUB_CLIENT_SECRET` | _empty_ |
| `SESSION_SECRET` | _empty_ |

## Migrations

```bash
alembic upgrade head
```

The initial migration (`alembic/versions/0001_initial.py`) creates the seven
tables defined in Build Spec §9.

## Layout

- `ab_server/main.py` — FastAPI app + CORS + router mounting.
- `ab_server/api/` — endpoint routers grouped by tag.
- `ab_server/models/` — SQLModel ORM definitions.
- `ab_server/auth/`, `ab_server/fetcher/`, `ab_server/rescoring/`,
  `ab_server/leaderboard/` — placeholders for Phase 1.

## References

- Build Spec §3 (package subtree), §9 (data model), §10 (API contract)
- ADR-004 (full web app), ADR-005 (modular monorepo), ADR-007 (pull-based aggregation)
