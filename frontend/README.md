# frontend

The command-centre UI. React + TypeScript + Vite, MapLibre for the map,
TanStack Query for the API, Tailwind for layout, i18next for English, Spanish
and Catalan.

```bash
npm install
npm run dev     # http://localhost:5173
```

It proxies to the API on **5102** — the port the asset-register contract fixes.
Set `BACKEND_URL` to point somewhere else. Start the backend first
(`cd ../backend && docker compose up -d`), or the app renders its error state.
[`../start.sh`](../start.sh) does both halves in one terminal instead.

| | |
|---|---|
| `npm run dev` | Vite dev server |
| `npm run build` | typecheck + production build |
| `npm test` | vitest |
| `npm run e2e` | Playwright smoke test (needs the backend up) |
| `npm run lint` | eslint |

## What it talks to

Only `/api` — the decision layer. It never calls `GET /assets` or
`/fire/arrival-grid` directly; those are the contract routes other people's
code uses.

```
GET  /api/health                      provenance badge in the header
GET  /api/config/defaults             the slider bounds
GET  /api/scenarios                   the ignition scenarios
GET  /api/scenarios/{id}/spread       arrival contours for the map
POST /api/scenarios/{id}/score        the ranked list and the summary
POST /api/scenarios/{id}/sensitivity  how stable that ranking is
POST /api/scenarios/{id}/briefing     the trilingual briefing
```

## Two things to know before changing it

**A scenario is not a fire.** Every ignition in this app is hypothetical —
nobody detected it. That is why the header says "Scenario", why no detection
time or containment status appears anywhere on screen, and why the hotspot
layer was removed rather than left permanently empty.
[../CONTEXT.md](../CONTEXT.md) has the vocabulary.

**Nothing in the asset register has a name.** All 4.27 M rows are called
`"residential"`. Named assets come from OpenStreetMap and arrive separately, so
the ranked list can be entirely anonymous if that query fails. `/score` reports
this as `named_layer: { available, count, error }` — a list with no names
because Overpass was unreachable must not look like a list with no critical
facilities nearby.

## Layout

```
src/
├── App.tsx              ranked list | map | controls, detail, charts, briefing
├── api/                 client.ts (fetch + ApiError), hooks.ts, types.ts
├── map/MapView.tsx      MapLibre: ICGC basemap, contours, assets by tier
├── components/          RankedList, ControlPanel, AssetDetail, ChartsPanel,
│                        BriefingPanel, Header
├── lib/ranks.ts         tier colours and rank-change tracking
└── i18n.ts              en / es / ca
```

The time scrubber in `ControlPanel` restyles the contours against `t`; it does
not refetch. Changing a scoring parameter does refetch — both `/score` and
`/sensitivity`, the latter costing seconds of server CPU, so the panel
debounces.
