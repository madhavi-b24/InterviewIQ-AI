# InterviewIQ AI — Frontend

React SPA against the backend's existing, already-tested API (see
`../docs/API.md`) — no backend behavior changes as the frontend is built.
Stack and layout follow `../docs/Architecture.md` §3/§7 exactly: React +
TypeScript + Vite, Tailwind CSS, React Router, Zustand (one slice per
feature), `@monaco-editor/react`, Vitest + React Testing Library.

## Setup

```bash
cp .env.example .env.development   # points at the local backend by default
npm install
npm run dev                         # http://localhost:5173
```

The backend must be running separately (`docker compose up` from the repo
root, or `uv run uvicorn app.main:app --reload` from `backend/`) — its
default CORS config already allows `http://localhost:5173`
(`backend/app/core/config.py::CORS_ORIGINS`).

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Local dev server with HMR |
| `npm run build` | Typecheck (`tsc -b`) + production build |
| `npm run typecheck` | Typecheck only |
| `npm run lint` | oxlint |
| `npm run test` | Vitest, single run |
| `npm run test:watch` | Vitest, watch mode |
| `npm run preview` | Serve the production build locally |

## Structure

```
src/
  app/          # router, root layout, shell chrome, 404
  components/   # shared design-system primitives (feature-agnostic)
  features/     # auth, resume, interview, coding, reports, dashboard —
                 # each owns its own api.ts + Zustand slice + components
  lib/          # API client, token storage, error normalization, env
  store/        # Zustand composition root (re-exports only)
  editor/       # Monaco wrapper (added when the coding round is built)
```

See the approved frontend implementation plan for the full route map,
per-feature design, and stage-by-stage build order — this is Stage 1
(foundation/scaffold) only; feature pages land in later stages.
