# ab-leaderboard

React + Vite SPA for the agent-benchmarks leaderboard, run launcher, trajectory viewer, trends, and settings surfaces.

## Stack

- React 18.3, TypeScript 5.5, Vite 5.3
- Tailwind 3.4 with shadcn-style CSS variables
- @tanstack/react-query, react-router-dom 6
- recharts, lucide-react, monaco-editor (for the Phase 1 trajectory viewer)
- vitest + @testing-library/react

## Getting started

```bash
pnpm install
pnpm dev
```

Dev server runs on `http://localhost:5173`. The five Phase 0 routes are:

- `/leaderboard`
- `/runs`
- `/trajectories`
- `/trends`
- `/settings`

## Scripts

| Script | What it does |
|--------|--------------|
| `pnpm dev` | Vite dev server |
| `pnpm build` | Production build to `dist/` |
| `pnpm preview` | Preview the built bundle |
| `pnpm typecheck` | `tsc -b --noEmit` |
| `pnpm lint` | ESLint over `.ts` / `.tsx` |
| `pnpm test` | Vitest in watch mode (`pnpm test -- --run` for one-shot) |

## Configuration

The API base URL is read from `import.meta.env.AB_API_BASE_URL` and defaults to `http://localhost:8000/api/v1`. Set it via Vite env files (`.env.local` with `AB_API_BASE_URL=...`); Vite is configured with `envPrefix: "AB_"`.

## Status

Phase 0 scaffolding only. Real data wiring lands in Phase 1 (rows 11–15 of the build spec).
