# Hackbarna_FireProtector

Wildfire values-at-risk tooling for Catalonia, built for the HackBarna 2026
Norrsken wildfire challenge. `backend/` is the asset-register API and its
database, both in Docker. `frontend/` is the UI.

This file is the map. [backend/README.md](backend/README.md) is the detail, and
you should read it before changing anything under `backend/`.

## What this system does

A fire spread forecast describes where a fire will be in N hours. The other
half of the question is **what is in that area that we care about.** This
backend serves both over HTTP, so a decision layer can rank what is at risk:

- an *asset register* — fixed things with a location, an importance and a
  susceptibility to fire — from Postgres (`GET /assets`);
- a *fire spread forecast* — `GET /fire/arrival-grid` runs a Deepfire ELMFIRE
  simulation from an ignition point and returns the hour the fire reaches each
  100 m cell.

## The one thing to know first

`GET /assets` implements a **contract shared with other people's code**: the
frontend and the decision layer are written against it. Its request and response
shapes are not ours to change unilaterally, and several of its rules fail
*silently* rather than loudly when broken. Those rules are listed under
[Contract invariants](backend/README.md#contract-invariants) — read them before
touching `backend/app/routers/assets.py` or `backend/app/schemas.py`.

## Current state

| Piece | State |
|---|---|
| `GET /assets` | Working. Serves 4,269,286 point assets. Points only — forests are not included |
| `GET /building_specs`, `POST /add_building` | Working. Internal, not part of the contract |
| `GET /fire/arrival-grid` | Working. Live call to Deepfire; needs `DEEPFIRE_CLIENT_ID`/`DEEPFIRE_CLIENT_SECRET` in `backend/.env`. Not part of the contract |
| `protection.asset_specs` | Loaded — the INSPIRE building register for Catalonia |
| `protection.forest_areas` | Loaded — the INSPIRE public forests of Catalonia. **Not served by any endpoint**; query it directly |
| `value` (importance) | **Placeholder.** Every loaded row is `1` |
| `vulnerability` | **Placeholder.** A column on both tables, filled with a random number 0–1 per row |
| Asset names | **Placeholder.** Every loaded row is `"residential"` — the source register has no names |

So the API is structurally complete and the data is real, but **nothing in a
response ranks anything yet**.

⚠️ `vulnerability` is **random**, which is more dangerous than a constant: it
varies per row, so responses look ranked and a chart of it looks plausible,
while meaning nothing. Anything built on it needs that caveat carried with it.
Both placeholders are `UPDATE`s away from being real — see [Replacing the
placeholders](backend/README.md#replacing-the-placeholders).

## Getting it running

Needs Docker, plus Python 3.11+ on the host for the loader.

```bash
./backend/scripts/setup_db.sh
```

One command: starts Postgres, applies the schema, loads both datasets
(~11 minutes for the assets, ~10 seconds for the forests), then builds and
starts the API. It is safe to re-run — already-loaded municipalities are
skipped, so a second run takes seconds.

When it finishes:

| | |
|---|---|
| Assets | http://localhost:5102/assets?bbox=1.0,41.6,1.6,42.0 |
| Fire spread | http://localhost:5102/fire/arrival-grid?lat=42.42&lon=2.87 (~20 s — it waits for the simulation) |
| API docs | http://localhost:5102/docs |
| Postgres | `postgresql://fireprotector:fireprotector@localhost:5432/fireprotector` |

Both bound to loopback. **Port 5102 is fixed by the contract** — the frontend
looks for the API there.

Already set up? `cd backend && docker compose up -d`.

## Repo map

```
backend/
├── app/                        # the FastAPI service
│   └── routers/assets.py       # GET /assets — THE CONTRACT ENDPOINT
├── fire_spread/                # GET /fire/arrival-grid — Deepfire, no database
├── db/init/*.sql               # schema; applied on every setup_db.sh run
├── extract_buildings.py        # INSPIRE building GML  -> CSV
├── extract_forests.py          # INSPIRE forest GeoJSON -> CSV
├── scripts/setup_db.sh         # one command: containers + schema + data
└── tests/                      # 94 tests, no database and no network needed
frontend/
docs/deepfire-api.md            # what the Deepfire API actually does
archive/docs/SPEC.md            # the original hackathon brief
```

## Conventions that hold across this repo

- **No PostGIS.** Coordinates are plain numeric columns; polygons are GeoJSON in
  a `jsonb` column. Bounding-box filtering happens in SQL, exact geometry work
  happens in Python with `shapely`. This is a deliberate, measured choice —
  [the reasoning is in backend/README.md](backend/README.md#why-no-postgis), and
  it is not an oversight to be fixed.
- **The database is the source of truth for shape.** Several code paths read the
  table's real columns from the Postgres catalog rather than hard-coding a
  schema, so adding a column does not require touching the API.
- **Loaders stream.** Source data is piped straight from the open-data portal
  into a parser and then `COPY`d; 12 GB of source GML never lands on disk.
- **Everything is re-runnable.** `setup_db.sh`, the schema files and both
  loaders can be run repeatedly without duplicating or corrupting data.
- **Secrets stay out of git.** `backend/.env` is the one file holding
  credentials, it is gitignored, and `backend/.env.example` lists what belongs
  in it. `docker-compose.yml` passes them into the container as environment
  variables rather than baking a `.env` into the image.
