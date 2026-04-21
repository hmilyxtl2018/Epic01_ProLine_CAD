# ProLine Dashboard — web/

Next.js 14 (App Router) front-end for the Dashboard backend in `app/`.

## Setup

```powershell
cd web
copy .env.local.example .env.local   # adjust NEXT_PUBLIC_API_BASE if needed
npm install
npm run dev
```

Open http://localhost:3000.

## Backend prerequisites

```powershell
# From repo root
.\scripts\dev_up.ps1 -Full -ServeApi   # brings up PostGIS + alembic + uvicorn
```

The web `npm run dev` server proxies `/api/*` to `NEXT_PUBLIC_API_BASE`
(default `http://localhost:8000`) via [next.config.js](next.config.js)
rewrites — so the browser stays same-origin and CORS isn't required.

## Role switcher (M1 trust model)

Roles are stamped into `X-Role` / `X-Actor` request headers from
`localStorage`. Use the header bar selector top-right to switch between
`viewer / operator / reviewer / admin`. Switching reloads the page so the
TanStack Query cache is rebuilt.

M3 (per ADR-006 deferral) replaces this with a real JWT-based login.

## Pages

| Route | Purpose |
|---|---|
| `/` | redirects to `/runs` |
| `/runs` | List + upload form (refreshes every 2 s while any run is non-terminal) |
| `/runs/[id]` | Detail view (refreshes every 2 s until terminal status) |

## Scripts

```powershell
npm run dev        # dev server + react-query devtools
npm run build      # production build
npm run typecheck  # tsc --noEmit
```
