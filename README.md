# Hackbarna_FireProtector

Wildfire values-at-risk tooling for Catalonia. `backend/` serves building data
over HTTP; `frontend/` is the UI.

## Getting started

Requires Docker (for the database) and Python 3.11+.

```bash
./scripts/setup_db.sh
```

That one command starts Postgres in Docker, creates the `protection` schema,
and loads the INSPIRE building register for Catalonia — about **4.25M
buildings** across **689 municipality files**. Then:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```

API docs land at http://localhost:8000/docs. See [backend/README.md](backend/README.md).

## The database

`docker-compose.yml` runs `postgres:18` on `127.0.0.1:5432` (loopback only) with
the data in a named volume, so it survives restarts.

| | |
|---|---|
| Database / user / password | `fireprotector` (override with `POSTGRES_*` env vars) |
| Schema | `protection` |
| Tables | `protection.building_specs`, `protection.load_log` |

```sql
protection.building_specs
    building         text PRIMARY KEY   -- INSPIRE localId, ID.BU.<slug>.<uuid>
    building_type    text               -- INSPIRE code; null for ~83% of rows
    latitude         double precision
    longitude        double precision
    municipality_id  text               -- 5-digit INE code, text for leading zeros
```

Open a psql shell with `docker compose exec db psql -U fireprotector`.

## `scripts/setup_db.sh`

```bash
./scripts/setup_db.sh                      # load everything still missing
./scripts/setup_db.sh --limit 10           # only the 10 smallest pending
./scripts/setup_db.sh --only solsona,olot  # named municipalities
./scripts/setup_db.sh --workers 8          # parallelism (default 4)
./scripts/setup_db.sh --reset              # wipe the volume and start over
```

For each municipality it streams the GML from
[datacloud.ide.cat](https://datacloud.ide.cat/geodades/inspire-edificis/)
**straight into `extract_buildings.py`** and loads the resulting CSV with
`COPY`. The 12 GB of source GML is never written to disk — only one small CSV
per municipality, deleted as soon as it lands.

It is **safe to re-run**. Every municipality is recorded in
`protection.load_log` inside the same transaction that inserts its buildings,
so an interrupted run resumes exactly where it stopped, and a finished one just
starts the container. Failures are reported at the end and retried by running
the script again.

Notes:

- First run also pulls `postgres:18` (~450 MB) and builds `scripts/.venv` with
  `lxml` and `shapely`.
- Needs about 5 GB free disk; the script warns and asks before starting if
  there is less.
- 680 of Catalonia's 947 municipalities publish building data, across 689
  files (Barcelona is split by district). The other 267 publish none.

## Layout

```
├── docker-compose.yml          # postgres:18
├── db/init/01_schema.sql       # protection schema, tables, indexes
├── scripts/setup_db.sh         # one-time database setup and data load
├── extract_buildings.py        # INSPIRE GML -> CSV
├── municipality_slug_map.csv   # municipality slug -> INE code
├── backend/                    # FastAPI service
└── frontend/
```
