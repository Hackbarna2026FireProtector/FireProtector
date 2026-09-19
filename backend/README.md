# FireProtector backend

FastAPI service over the Catalonia building register and the public forests of
Catalonia. The API and Postgres both run in Docker, defined in
`docker-compose.yml`.

## Setup

From the repo root:

```bash
./backend/scripts/setup_db.sh
```

This starts Postgres, creates the `protection` schema, loads the building and
forest data, then builds and starts the API. Everything is up when it finishes:

- Interactive docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

Both ports are bound to loopback.

## Day to day

```bash
cd backend
docker compose up -d          # start (data is already in the volume)
docker compose logs -f api    # follow API logs
docker compose down           # stop; the volume and its data survive
docker compose exec db psql -U fireprotector
```

`app/` is mounted into the container and uvicorn runs with `--reload`, so code
edits take effect without a rebuild. Rebuild only when `requirements.txt`
changes:

```bash
docker compose up -d --build api
```

### Running the API on the host instead

Useful for a debugger. The database still comes from Docker.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # already points at localhost:5432
.venv/bin/uvicorn app.main:app --reload
```

`.env` is gitignored — keep connection strings out of commits. The container
ignores it and takes its settings from `docker-compose.yml`.

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

## The tables

Both are loaded from INSPIRE by `scripts/setup_db.sh`. No PostGIS is required
anywhere: coordinates are plain numeric columns and polygons are GeoJSON.

### `protection.building_specs`

4,269,286 buildings.

| Column | Type | Notes |
|---|---|---|
| `building` | `text` | Primary key. INSPIRE localId, `ID.BU.<slug>.<uuid>` |
| `building_type` | `text` | INSPIRE code (`shed`, `storageTank`, …); null for ~83% of rows |
| `latitude` | `double precision` | Point on the footprint, not the centroid |
| `longitude` | `double precision` | |
| `municipality_id` | `text` | 5-digit INE code; text, because 56 begin with a zero |

If the table is missing, both routes return **503** naming the table and
columns they looked for. Point `BUILDING_SPECS_TABLE` / `LATITUDE_COLUMN` /
`LONGITUDE_COLUMN` elsewhere to read a different table. The bounding-box filter
is served by `building_specs_lat_lon_idx`.

### `protection.forest_areas`

The 1,185 public forests of Catalonia, 523,988 ha in all — the INSPIRE *Forest
management areas* dataset (theme AM), published by the Departament
d'Agricultura, Ramaderia, Pesca i Alimentació under CC BY 4.0.

| Column | Type | Notes |
|---|---|---|
| `forest_id` | `text` | Primary key. INSPIRE localId, `ID.AM.forest.<n>` |
| `name` | `text` | e.g. `OBAGA I SOLANA` |
| `cup_code` | `text` | Number in the Catàleg de Forests d'Utilitat Pública; null for the 508 that are not catalogued |
| `elenc_code` | `text` | Number in the Elenc de forests de titularitat pública |
| `has_agreement` | `boolean` | Privately owned, managed by the Generalitat under an agreement (531) |
| `has_management_plan` | `boolean` | Covered by an approved forest management plan (462) |
| `certification` | `text` | `Sistema de Certificació PEFC` for 49 forests, else null |
| `area_ha` | `double precision` | From the geometry, through an equal-area projection |
| `latitude`, `longitude` | `double precision` | A point guaranteed to be **inside** the forest. Named to match `building_specs`, so the same bounding-box query serves both tables |
| `min_latitude` … `max_longitude` | `double precision` | The forest's envelope |
| `version_id` | `text` | INSPIRE versionId of the source feature, e.g. `20250714` |
| `geometry` | `jsonb` | GeoJSON MultiPolygon, ETRS89 geographic, lon/lat; ~17 kB each |

There is no index beyond the primary key, on purpose: at 1,185 rows a scan of
everything but the geometry takes a fraction of a millisecond.

The polygons are the expensive column, so narrow with the envelope in SQL and
test exactly in Python:

```sql
SELECT forest_id, name, geometry
FROM protection.forest_areas
WHERE max_latitude  >= %(min_lat)s AND min_latitude  <= %(max_lat)s
  AND max_longitude >= %(min_lon)s AND min_longitude <= %(max_lon)s;
```

```python
from shapely.geometry import Point, shape
from shapely.prepared import prep

forest = prep(shape(row["geometry"]))      # jsonb arrives as a dict
at_risk = [b for b in buildings if forest.covers(Point(b["longitude"], b["latitude"]))]
```

This is the **public forest estate**, not a vegetation or fuel map: it covers
the forests the Generalitat manages, a fraction of Catalonia's forest cover.
For continuous land cover the same service publishes
`inspire:LC.LandCoverSurfaces`.

## Tests

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

## Layout

```
backend/
├── docker-compose.yml           # db (postgres:18) + api
├── Dockerfile                   # the API image
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
├── db/
│   ├── init/
│   │   ├── 01_schema.sql        # protection schema, building_specs, load_log
│   │   └── 02_forests.sql       # forest_areas
│   └── import/                  # loader staging area (gitignored)
├── data/
│   └── municipality_slug_map.csv
├── scripts/setup_db.sh          # one-time setup and data load
├── extract_buildings.py         # INSPIRE building GML  -> CSV
├── extract_forests.py           # INSPIRE forest GeoJSON -> CSV
└── tests/
    ├── test_geo.py
    └── test_payload.py
```

## Loading the data

`scripts/setup_db.sh` is safe to re-run; it skips municipalities already in
`protection.load_log`.

```bash
./backend/scripts/setup_db.sh                 # load everything still missing
./backend/scripts/setup_db.sh --limit 10      # only the 10 smallest pending
./backend/scripts/setup_db.sh --only olot     # named municipalities
./backend/scripts/setup_db.sh --workers 8     # parallelism (default 4)
./backend/scripts/setup_db.sh --forests-only  # refresh the forests, skip buildings
./backend/scripts/setup_db.sh --no-forests    # buildings only
./backend/scripts/setup_db.sh --reset         # wipe the volume and start over
```

**Buildings.** Each municipality is streamed from
[datacloud.ide.cat](https://datacloud.ide.cat/geodades/inspire-edificis/)
straight into `extract_buildings.py` and loaded with `COPY`, so the 12 GB of
source GML never touches the disk. The insert and its `load_log` row share one
transaction, making an interrupted run resumable.

680 of Catalonia's 947 municipalities publish building data, across 689 files
(Barcelona is split by district); the other 267 publish none.

**Forests.** One request to the [INSPIRE OGC API - Features
endpoint](https://geoserveis.ide.cat/servei/catalunya/inspire/ogc/features/collections/inspire:AM.ForestManagementArea)
of the same service brings all 1,185 polygons as GeoJSON, which
`extract_forests.py` turns into a CSV. The table is then replaced wholesale in
one transaction, so a re-run also drops forests the source no longer lists;
the whole step takes about ten seconds.

The GML served by [the dataset's ATOM
feed](https://geoserveis.ide.cat/servei/catalunya/inspire-zones-subjectes-ordenacio/atom/inspire-forests-dataset.atom.xml)
holds the same polygons but only the harmonised INSPIRE core — no CUP number,
management plan or certification — which is why the loader reads GeoJSON here
and GML for the buildings. Both are listed on [the dataset's metadata
record](https://www.idee.es/csw-codsi-idee/srv/eng/catalog.search#/metadata/inspire-forests).
