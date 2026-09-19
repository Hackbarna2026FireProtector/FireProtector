# FireProtector backend

FastAPI service over the building register in Postgres.

## Setup

Start the database first — from the repo root:

```bash
./scripts/setup_db.sh
```

Then:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

The defaults in `.env.example` already point at the local Docker database, so
no editing is needed. `.env` is gitignored — keep connection strings out of
commits.

## Run

```bash
.venv/bin/uvicorn app.main:app --reload --port 8000
```

- Interactive docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## `GET /building_specs`

Returns every row of the building table whose point falls inside a square of
`size_km` × `size_km` centred on the given coordinate.

| Parameter | Required | Description |
|---|---|---|
| `lat` | yes | Latitude of the centre, −90…90 (WGS84 degrees) |
| `lon` | yes | Longitude of the centre, −180…180 |
| `size_km` | yes | Side length of the square in km (the centre is in the middle, so the box extends `size_km / 2` in each direction) |
| `limit` | no | Max rows; defaults to `DEFAULT_LIMIT` (500), capped at `MAX_LIMIT` (10000) |

```bash
curl "http://localhost:8000/building_specs?lat=41.80&lon=1.25&size_km=10"
```

```json
{
  "center": { "latitude": 41.8, "longitude": 1.25 },
  "size_km": 10.0,
  "bounds": {
    "min_latitude": 41.75503398181377,
    "max_latitude": 41.84496601818623,
    "min_longitude": 1.1896814676725258,
    "max_longitude": 1.3103185323274742
  },
  "count": 2,
  "limit": 500,
  "truncated": false,
  "buildings": [
    { "id": 1, "name": "Centre point", "latitude": 41.8, "longitude": 1.25, "...": "all table columns" }
  ]
}
```

Notes:

- The north-south side is exactly `size_km`; the east-west side is `size_km`
  measured along the parallel through the centre, so the box is square on the
  ground rather than in degrees.
- Rows come back nearest-to-centre first, with **all** table columns as stored —
  the endpoint does not need changing when the dataset gains columns.
- `truncated: true` means the row cap was hit and more buildings may lie in the box.

## `POST /add_building`

Inserts one building, or a list of them, into the same table `/building_specs`
reads. The body's keys must be columns of that table; `latitude` and `longitude`
are required, everything else is optional and falls back to the column's
database default.

```bash
curl -X POST http://localhost:8000/add_building \
  -H 'Content-Type: application/json' \
  -d '{"name": "Hospital Comarcal", "building_type": "hospital",
       "latitude": 41.84, "longitude": 1.30, "floors": 5}'
```

```json
{
  "inserted": 1,
  "buildings": [
    { "id": 1, "name": "Hospital Comarcal", "building_type": "hospital",
      "latitude": 41.84, "longitude": 1.3, "floors": 5, "created_at": "..." }
  ]
}
```

Send a JSON array to load several at once (up to `MAX_INSERT_ROWS`, default 1000):

```bash
curl -X POST http://localhost:8000/add_building \
  -H 'Content-Type: application/json' \
  -d '[{"name": "Escola Segarra", "latitude": 41.82, "longitude": 1.27},
       {"name": "Substation East", "latitude": 41.78, "longitude": 1.31}]'
```

Notes:

- Responds **201** with the rows as stored, so you get back database-generated
  values (ids, defaults, timestamps, generated columns).
- Rows in one request need not have the same keys; a row that omits a column
  gets that column's default.
- A batch is **atomic** — if any row fails, none are written.
- The body is validated against the table's real columns, read from the
  catalog, so a typo comes back as a 400 naming the valid columns rather than a
  raw Postgres error.

| Status | Meaning |
|---|---|
| 201 | Rows inserted |
| 400 | Bad column name, missing/out-of-range coordinates, or a constraint violation (not-null, check, foreign key) |
| 409 | Unique constraint violation (e.g. a duplicate id) |
| 422 | Malformed JSON body |
| 503 | Table not found, or the database is unreachable |


## Configuration

All settings come from the environment or `.env` (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | Postgres connection string (required) |
| `BUILDING_SPECS_TABLE` | `building_specs` | Table to read; `schema.table` is accepted (set to `protection.building_specs`) |
| `LATITUDE_COLUMN` | `latitude` | Latitude column name |
| `LONGITUDE_COLUMN` | `longitude` | Longitude column name |
| `DEFAULT_LIMIT` | `500` | Row cap when `limit` is not given |
| `MAX_LIMIT` | `10000` | Hard row cap |
| `MAX_INSERT_ROWS` | `1000` | Max rows per `POST /add_building` |
| `POOL_MIN_SIZE` / `POOL_MAX_SIZE` | `1` / `10` | Connection pool sizing |
| `CORS_ORIGINS` | `["*"]` | Browser origins allowed to call the API |

## The table

`protection.building_specs`, loaded from INSPIRE by `scripts/setup_db.sh`:

| Column | Type | Notes |
|---|---|---|
| `building` | `text` | Primary key. INSPIRE localId, `ID.BU.<slug>.<uuid>` |
| `building_type` | `text` | INSPIRE code (`shed`, `storageTank`, …); null for ~83% of rows |
| `latitude` | `double precision` | Point on the footprint, not the centroid |
| `longitude` | `double precision` | |
| `municipality_id` | `text` | 5-digit INE code; text, because 56 begin with a zero |

If the table is missing, both routes return **503** naming the table and
columns they looked for. Point `BUILDING_SPECS_TABLE` / `LATITUDE_COLUMN` /
`LONGITUDE_COLUMN` elsewhere to read a different table.

No PostGIS is required: the filter is a plain bounding box on two numeric
columns, served by `building_specs_lat_lon_idx`.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

## Layout

```
backend/
├── app/
│   ├── main.py                  # app factory, lifespan, CORS, /health
│   ├── config.py                # settings from env / .env
│   ├── db.py                    # async connection pool
│   ├── errors.py                # database errors -> HTTP status codes
│   ├── geo.py                   # centre + size_km -> bounding box
│   ├── payload.py               # POST body validation (pure functions)
│   ├── queries.py               # the SELECT, the INSERT, column introspection
│   ├── schemas.py               # response models
│   └── routers/
│       ├── building_specs.py
│       └── add_building.py
└── tests/
    ├── test_geo.py
    └── test_payload.py
```
