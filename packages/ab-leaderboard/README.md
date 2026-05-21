# ab-leaderboard

React + Vite SPA for the agent-benchmarks **Leaderboard · Run Launcher · Trajectory Viewer · Trends · Settings**.
Owned by the `claude-designer` agent (CLAUDE.md §"What ships and what doesn't"). The package is wired against the FastAPI server in `packages/ab-server` but ships with offline-friendly mock data, so a designer can iterate without a live backend.

## Stack

- React 18.3 · TypeScript 5.5 strict · Vite 5.3
- Tailwind 3.4 with shadcn-style HSL tokens (`src/styles/globals.css`)
- `@tanstack/react-query` v5 · `react-router-dom` v6
- `recharts`, `lucide-react`, `monaco-editor` (loaded on the trajectory diff view)
- `vitest` + `@testing-library/react`

## Five surfaces

| Route | Page | Surfaces from PRD §10 |
|---|---|---|
| `/leaderboard`   | `pages/Leaderboard.tsx`        | Matrix or Cards (Tweak) · per-pillar scores · trust dot (●/◐/○) · operator column · stale-dataset pill · Pareto cost/correctness · hot-regressions rail |
| `/runs`          | `pages/RunLauncher.tsx`        | Two-pane: task tree + configurator · `New run` / `Replay from commit` modes · live cost estimate · live-run banner |
| `/tasks`         | `pages/Tasks.tsx`              | Library browser variant of the task tree |
| `/trajectories`  | `pages/TrajectoryViewer.tsx`   | 3-pane or stacked (Tweak) · provenance breadcrumb · turn timeline · vault diff · scorer chain · pillar radar · cost ledger · privacy-scrubber preview |
| `/trends`        | `pages/Trends.tsx`             | 30d correctness chart with per-operator overlay · Pareto trails · regressions / improvements · alert rules · model × suite heatmap |
| `/settings`      | `pages/Settings.tsx`           | Account · Connected repos · Privacy (scrubber rules) · stubs for Models / MCP / Skills / Vaults / CI / Alerts |

## Design system

- Tokens live in `src/styles/globals.css` as HSL channels (`--background`, `--foreground`, `--accent`, `--pass`, `--fail`, `--warn`, `--info`, `--idle`, plus vendor accents).
- Tailwind config consumes them via `hsl(var(--…))`; `dark` mode is class-driven (`.theme-dark` / `.theme-light`).
- Density is `data-density="compact|regular|comfortable"` on `<html>`.
- Primitives live under `src/components/ui/`; domain-specific bits under `src/components/domain/`; charts under `src/components/charts/`; per-surface code under `src/components/{leaderboard,launcher,trajectory,trends,settings}/`.
- Trust tier, layer, tier, scorer kinds match `docs/schemas/*.schema.json` 1:1 (`self_reported` / `verified` / `official`, `L0…L5`, `T0…T3`).

## API contract

URL builders live in `src/api/client.ts`. They mirror the server endpoints landed in M2:

```
GET  /api/v1/leaderboard                  (?suites&models&operators&trust_tiers&dataset_current_only&range)
GET  /api/v1/leaderboard/pareto
GET  /api/v1/trends/overview
GET  /api/v1/trends                       (?range&show_operators)
GET  /api/v1/trends/regressions           (?direction=up|down&window_days)
GET  /api/v1/trends/ci-gate
GET  /api/v1/runs                         (?status=scheduled|in_progress|recent)
POST /api/v1/runs
POST /api/v1/runs/estimate
GET  /api/v1/runs/{id}
GET  /api/v1/runs/{id}/stream             (SSE)
GET  /api/v1/runs/{run_id}/trajectories/{task_id}
GET  /api/v1/submissions/{id}
GET  /api/v1/submissions/{id}/trajectory
GET  /api/v1/submissions/{id}/privacy-scan
GET  /api/v1/tasks
GET  /api/v1/tasks/{id}
GET  /api/v1/tiers
GET  /api/v1/presets   POST /api/v1/presets   PATCH …   DELETE …
GET  /api/v1/alerts    POST /api/v1/alerts    PATCH …   DELETE …
POST /api/v1/alerts/evaluate
```

React Query hooks in `src/api/hooks.ts` consume them with `placeholderData` from `src/lib/mock-data.ts`, so every page renders fully populated when the server is down. To force mock data even when the server is reachable:

```bash
# .env.local
AB_USE_MOCK=1
```

## Getting started

```bash
cd packages/ab-leaderboard
pnpm install
pnpm dev          # http://localhost:5173
```

## Scripts

| Script | What it does |
|--------|--------------|
| `pnpm dev` | Vite dev server |
| `pnpm build` | Production build to `dist/` |
| `pnpm preview` | Preview the built bundle |
| `pnpm typecheck` | `tsc --noEmit` |
| `pnpm lint` | ESLint over `.ts` / `.tsx` |
| `pnpm test` | Vitest in watch mode (`pnpm test -- --run` for one-shot) |

## Configuration

```bash
# .env.local
AB_API_BASE_URL=http://localhost:8000/api/v1   # default
AB_USE_MOCK=1                                  # force mock data
```

## Privacy boundary

Three-layer enforcement per LSN-006:

1. **Pre-commit** — repo-wide hook scans staged diffs against `docs/privacy-patterns.yaml`. Refuses commits matching maintainer paths, emails, API tokens.
2. **`privacy_check` scorer** — every trajectory headed for publication runs it; required to pass before `ab publish` will push.
3. **CI `privacy-scan` workflow** — same patterns run on every PR; matches block merge.

Mock data in `src/lib/mock-data.ts` uses `<placeholder>` paths for the scrubber demo (`/Users/<placeholder>/vault/…`) precisely so the patterns above don't false-positive on this code.

## Status

Phase 1 M3 — design implementation. Surfaces are wired against the M2 server contract; live data swap is a one-line change at each call site (`useLeaderboard()` → strip `placeholderData` to require fresh fetch).
