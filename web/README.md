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
npm run build:mlight  # rebuild the local MLightCAD bundle (see below)
```

## CAD preview — dual rendering engines

The Sites detail page (`/sites/[runId]`) embeds **two** open-source DXF
renderers behind a toolbar toggle so we can compare them side-by-side on
real customer files before committing to one. **Note: this A/B is purely
at the rendering layer** — both engines read the same DXF file and the
left-side ontology panel is unchanged. A second ontology source
(MLightCAD-derived semantic JSON) is on the roadmap (Phase 1 spike).

| Engine     | Stack                          | Strengths                                | Weaknesses                              |
|------------|--------------------------------|------------------------------------------|-----------------------------------------|
| dxf-viewer | Three.js + React (in-bundle)   | Lightweight, no iframe, fast init        | FitView struggles with outlier extents  |
| MLightCAD  | Vue 3 + Element Plus + WASM    | Full UI (layers, command line, zoom-extents), libredwg DWG support | Heavier (~4 MB JS), runs in iframe |

Default engine: **MLightCAD** — its built-in zoom-extents handles
DWG-converted DXFs with skewed bounding boxes more reliably than
dxf-viewer's FitView.

### MLightCAD bundle (zero CDN)

The Vue + Element Plus + `@mlightcad/*` tree is bundled locally to
`public/mlight/bundle.{js,css}` (≈4 MB JS + 360 KB CSS) by
[scripts/build-mlight.mjs](scripts/build-mlight.mjs). Three Web Workers
(DXF parser, libredwg DWG parser, MText renderer) are copied to
`public/mlight/workers/`. The iframe page
[public/mlight-viewer.html](public/mlight-viewer.html) loads them
without touching any external CDN.

Run after MLightCAD or related deps change:

```powershell
npm run build:mlight
```

The bundle is committed-on-build for now (no separate build step in CI).
Three.js is pinned to **0.172.0** to satisfy `@mlightcad/cad-simple-viewer`'s
peer requirement — do not bump unless MLightCAD is also updated.
