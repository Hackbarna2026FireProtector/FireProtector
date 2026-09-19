# Hackbarna_FireProtector

Wildfire values-at-risk tooling for Catalonia. `backend/` is the asset-register
API and its database, both in Docker; `frontend/` is the UI.

## Getting started

Docker is the only requirement (plus Python 3.11+ on the host, which the data
loader uses to parse the source GML).

```bash
./backend/scripts/setup_db.sh
```

That one command starts Postgres, creates the `protection` schema, loads two
INSPIRE datasets for Catalonia — **4,269,286 point assets** across 689
municipality files (about 11 minutes) and the **1,185 public forests**, 523,988
ha of polygons (about ten seconds) — then builds and starts the API.

When it finishes:

| | |
|---|---|
| Assets | http://localhost:5102/assets?bbox=1.0,41.6,1.6,42.0 |
| API docs | http://localhost:5102/docs |
| Postgres | `postgresql://fireprotector:fireprotector@localhost:5432/fireprotector` |
| Tables | `protection.asset_specs`, `protection.forest_areas` |

Both are bound to loopback only. Port 5102 is the one the asset-register
contract names, so the frontend and the decision layer find the API where they
expect it.

`GET /assets?bbox=minLon,minLat,maxLon,maxLat` returns a GeoJSON
`FeatureCollection` of the point assets and forest polygons in the box, paged
at 1000 features with a `next` link — **a consumer that ignores `next` reads
only the first page**. `value` and `vulnerability` are placeholders until the
risk model lands; see [backend/README.md](backend/README.md) for the full
contract notes and the other two routes.

## Layout

```
backend/
├── docker-compose.yml          # db (postgres:18) + api services
├── Dockerfile                  # the FastAPI image
├── app/                        # FastAPI application (GET /assets lives here)
├── db/
│   ├── init/                   # protection schema, tables, indexes
│   └── import/                 # loader staging area (gitignored)
├── data/
│   └── municipality_slug_map.csv
├── scripts/setup_db.sh         # one-time setup and data load
├── extract_buildings.py        # INSPIRE building GML  -> CSV
├── extract_forests.py          # INSPIRE forest GeoJSON -> CSV
└── tests/
frontend/
```

Everything the backend needs lives under `backend/`, so the stack is brought up
from there and the repo root stays free for the other pieces.
