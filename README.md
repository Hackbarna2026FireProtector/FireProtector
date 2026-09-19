# Hackbarna_FireProtector

Wildfire values-at-risk tooling for Catalonia. `backend/` is the API and its
database, both in Docker; `frontend/` is the UI.

## Getting started

Docker is the only requirement (plus Python 3.11+ on the host, which the data
loader uses to parse the source GML).

```bash
./backend/scripts/setup_db.sh
```

That one command starts Postgres, creates the `protection` schema, loads two
INSPIRE datasets for Catalonia — **4,269,286 buildings** across 689 municipality
files (about 11 minutes) and the **1,185 public forests**, 523,988 ha of
polygons (about ten seconds) — then builds and starts the API.

When it finishes:

| | |
|---|---|
| API docs | http://localhost:8000/docs |
| Postgres | `postgresql://fireprotector:fireprotector@localhost:5432/fireprotector` |
| Tables | `protection.building_specs`, `protection.forest_areas` |

Both are bound to loopback only. See [backend/README.md](backend/README.md) for
the endpoints.

## Layout

```
backend/
├── docker-compose.yml          # db (postgres:18) + api services
├── Dockerfile                  # the FastAPI image
├── app/                        # FastAPI application
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
