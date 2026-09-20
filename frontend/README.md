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

The ranked list acts on that field. When `available` is false it shows a
"names unavailable" banner above the rows and falls back to the asset id, set
in a mono face, for every row — including the ones whose register `name`
happens to differ from their type, because a storage tank labelled
"residential" is still the register's placeholder and not a name. Rows are
told apart by id, distance from the ignition point, ETA and risk, since name,
type, value and vulnerability are identical across thousands of them.

## Layout

```
src/
├── App.tsx              ranked list | map | controls, detail, charts, briefing
├── api/                 client.ts (fetch + ApiError), hooks.ts, types.ts
├── map/MapView.tsx      MapLibre: ICGC basemap, contours, assets by tier,
│                        the other scenarios' ignition points
├── components/          RankedList, ControlPanel, AssetDetail, ChartsPanel,
│   │                    BriefingPanel, Header, MapLegend
│   └── ui/              local primitives — Button, Badge, Card, Select,
│                        Slider, Checkbox
├── lib/ranks.ts         tier colours, rank-change tracking, name fallback
├── lib/geo.ts           distance from the ignition point
└── i18n.ts              en / es / ca
```

`components/ui/` is shadcn/ui's shape without its dependencies: the same
variant-prop call sites (`<Button variant="ghost">`, `<Badge variant="critical">`)
over native elements and this project's Tailwind tokens. `cn()` is eight lines
instead of `clsx` + `tailwind-merge`, so it joins class names but does not
resolve conflicts — the note at the top of `ui/cn.ts` says what that costs and
what swapping the real library in would take. The sliders and the two selects
are native controls, which is where the keyboard behaviour comes from; adopting
Radix would mean adding `@radix-ui/react-slider` and friends.

Every scenario's ignition point is on the map, not just the one being viewed.
The others are hollow amber rings, off-screen at the zoom `fitBounds` lands on
and coming into view as you zoom out; clicking one switches scenario, exactly
as the header picker does. They are a separate source from the active
`ignition` so the two can be styled and hit-tested apart. The basemap is raster
and the style sets no `glyphs`, so their labels are MapLibre popups on hover —
a `text-field` symbol layer would render nothing.

The time scrubber in `ControlPanel` restyles the contours against `t`; it does
not refetch. Changing a scoring parameter does refetch — both `/score` and
`/sensitivity`, the latter costing seconds of server CPU, so the panel
debounces.
