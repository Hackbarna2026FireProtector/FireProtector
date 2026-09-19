# FireProtector backend

Asset-register API for the wildfire values-at-risk tool, over the Catalonia
building register and the public forests of Catalonia. `GET /assets` implements
the shared asset-register contract; the other two routes are internal. The API
and Postgres both run in Docker, defined in `docker-compose.yml`.

## Setup

From the repo root:

```bash
./backend/scripts/setup_db.sh
```

This starts Postgres, creates the `protection` schema, loads the asset and
forest data, then builds and starts the API. Everything is up when it finishes:

- Assets: http://localhost:5102/assets?bbox=1.0,41.6,1.6,42.0
- Interactive docs: http://localhost:5102/docs
- Health check: http://localhost:5102/health

Port 5102 is the one the asset-register contract names, so the frontend and the
decision layer find the API where they expect it. Both ports are bound to
loopback.

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

## `GET /assets`

The contract endpoint. Returns a GeoJSON `FeatureCollection` of the assets
inside a bounding box: point assets from `protection.asset_specs` and forest
polygons from `protection.forest_areas`, in one response.

| Parameter | Required | Description |
|---|---|---|
| `bbox` | yes | `minLon,minLat,maxLon,maxLat` in EPSG:4326 degrees — **longitude first**, the opposite order of `/building_specs` |
| `limit` | no | Features per page. Defaults to `ASSETS_PAGE_SIZE` (1000), which is also the ceiling |
| `offset` | no | Features to skip. Defaults to 0 |

```bash
curl "http://localhost:5102/assets?bbox=2.78,41.69,2.84,41.74&limit=2"
```

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [2.7867, 41.736] },
      "properties": {
        "asset_id": "asset-1869264",
        "asset_type": "residential",
        "name": "residential",
        "value": 1.0,
        "vulnerability": 0.5,
        "source": "INSPIRE"
      }
    }
  ],
  "numberMatched": 13854,
  "numberReturned": 2,
  "next": "http://localhost:5102/assets?bbox=2.78%2C41.69%2C2.84%2C41.74&offset=2&limit=2"
}
```

### Things a consumer needs to know

- **Follow `next`.** The contract has no paging, so a bare `?bbox=` request
  returns the first 1000 features and looks complete. A 50 × 44 km box holds
  around 127,000 features, which is 127 pages. `next` is `null` on the last one.
- **`numberMatched` / `numberReturned`** are extra top-level fields. The
  contract does not forbid them, so a consumer validating against it still
  passes.
- **Almost no `asset_type` is in the contract's enum.** Every value is
  `residential`, `forest`, or an INSPIRE building nature (`shed`, `canopy`,
  `storageTank`, `greenhouse`, `tower`) — the enum is explicitly open, so
  consumers take their unknown-type path for effectively all of our data.
- **`value` is 1 and `vulnerability` is 0.5 for everything loaded.** Neither is
  scored yet, so nothing in a response ranks anything. See
  [Vulnerability](#vulnerability) below.
- **`asset_id` is prefixed** — `asset-<id>` for points, `forest-<localId>` for
  forests — so the two layers cannot collide. Ids are unique within a response,
  which the contract requires.
- **Paging is ordered by `asset_id`** so a page never repeats or skips a row.
  The order is lexical, so every point precedes every forest.

### Vulnerability

`app/vulnerability.py` is a **stub**: it returns 0.5 for everything. The real
model replaces the body of `vulnerability(asset)` and nothing else changes —
the endpoint calls it once per feature and hands it the whole row, so a model
that needs coordinates, municipality or provenance can read them without
touching any caller. The return value is clamped to 0–1, so a replacement that
returns something out of range cannot produce a response the consumer rejects.

## Errors

Every error uses the contract's envelope, on all three routes:

```json
{ "error": { "code": "bad_request", "message": "'bbox' is malformed: expected minLon,minLat,maxLon,maxLat in EPSG:4326 degrees, got 'nonsense'." } }
```

| Status | `code` | When |
|---|---|---|
| 400 | `bad_request` | Missing or malformed `bbox`, `limit`/`offset` that is not a whole number or is out of range, a bad column or coordinate in a POST body, or a constraint violation |
| 404 | `not_found` | Unknown path |
| 409 | `conflict` | Unique constraint violation |
| 500 | `internal_error` | Unhandled error. The detail is logged, not returned |
| 503 | `unavailable` | Table not found, or the database is unreachable |

FastAPI's usual 422 for a validation failure is reported as **400**, because
the contract defines only 400 and 500.

## `GET /building_specs`

Internal route, not part of the contract. Returns every row of the asset table
whose point falls inside a square of `size_km` × `size_km` centred on the given
coordinate — a centre and a radius rather than a box, which suits a map UI.

| Parameter | Required | Description |
|---|---|---|
| `lat` | yes | Latitude of the centre, −90…90 (WGS84 degrees) |
| `lon` | yes | Longitude of the centre, −180…180 |
| `size_km` | yes | Side length of the square in km (the centre is in the middle, so the box extends `size_km / 2` in each direction) |
| `limit` | no | Max rows; defaults to `DEFAULT_LIMIT` (500), capped at `MAX_LIMIT` (10000) |

```bash
curl "http://localhost:5102/building_specs?lat=41.80&lon=1.25&size_km=10"
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
    {
      "asset_id": 1869264, "source_id": "ID.BU.lloret-de-mar.a1b2", "name": "residential",
      "asset_type": "residential", "value": 1, "source": "INSPIRE",
      "latitude": 41.8, "longitude": 1.25, "municipality_id": "17095"
    }
  ]
}
```

Notes:

- The north-south side is exactly `size_km`; the east-west side is `size_km`
  measured along the parallel through the centre, so the box is square on the
  ground rather than in degrees.
- Rows come back nearest-to-centre first, with **all** table columns as stored —
  the endpoint does not need changing when the dataset gains columns.
- `truncated: true` means the row cap was hit and more assets may lie in the box.
- Rows are the table as stored, so they carry `asset_id`/`source_id`/`asset_type`
  rather than the old `building`/`building_type`, and no `vulnerability` — that
  is computed by `/assets` only. Forests are not included here.

## `POST /add_building`

Internal route, not part of the contract. Inserts one asset, or a list of them,
into the same table `/assets` and `/building_specs` read — the write path for
real named assets, which the INSPIRE register does not provide. The body's keys
must be columns of that table; `latitude` and `longitude` are required,
everything else is optional and falls back to the column's database default.

`asset_id` is generated, so it cannot be supplied. `source` defaults to
`INSPIRE`, so pass your own (`"manual"`, `"osm"`, …) for anything that is not
from the register.

```bash
curl -X POST http://localhost:5102/add_building \
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
curl -X POST http://localhost:5102/add_building \
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
| 400 | Bad column name, missing/out-of-range coordinates, a malformed body, or a constraint violation |
| 409 | Unique constraint violation (e.g. a duplicate `source_id`) |
| 503 | Table not found, or the database is unreachable |

All of them use the [error envelope](#errors).


## Configuration

All settings come from the environment or `.env` (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | Postgres connection string (required) |
| `ASSET_SPECS_TABLE` | `protection.asset_specs` | Point assets; `schema.table` is accepted |
| `FOREST_AREAS_TABLE` | `protection.forest_areas` | Forest polygons, unioned in by `/assets` |
| `LATITUDE_COLUMN` | `latitude` | Latitude column name |
| `LONGITUDE_COLUMN` | `longitude` | Longitude column name |
| `DEFAULT_LIMIT` | `500` | Row cap when `limit` is not given |
| `MAX_LIMIT` | `10000` | Hard row cap for `/building_specs` |
| `ASSETS_PAGE_SIZE` | `1000` | Page size for `/assets`; also its ceiling |
| `MAX_INSERT_ROWS` | `1000` | Max rows per `POST /add_building` |
| `POOL_MIN_SIZE` / `POOL_MAX_SIZE` | `1` / `10` | Connection pool sizing |
| `CORS_ORIGINS` | `["*"]` | Browser origins allowed to call the API |
| `API_PORT` | `5102` | Host port in `docker-compose.yml` |

## The tables

Both are loaded from INSPIRE by `scripts/setup_db.sh`. No PostGIS is required
anywhere: coordinates are plain numeric columns and polygons are GeoJSON.

### `protection.asset_specs`

4,269,286 point assets — the INSPIRE building register, migrated in place from
the original `building_specs` when the API adopted the contract.

| Column | Type | Notes |
|---|---|---|
| `asset_id` | `bigint` | Generated primary key. Served as `asset-<id>` |
| `source_id` | `text` | INSPIRE localId, `ID.BU.<slug>.<uuid>`. Unique, so the loader upserts on it and a re-run cannot duplicate a municipality. Null for assets added through `/add_building` |
| `name` | `text` | `'residential'` for every loaded row — the register carries no names at all |
| `asset_type` | `text` | INSPIRE building nature (`shed`, `storageTank`, `tower`, …), `'residential'` for the 3,674,190 rows the source leaves untyped |
| `value` | `numeric` | Relative importance, 1–100. Defaults to **1**, meaning "not scored yet" |
| `source` | `text` | Provenance. Defaults to `'INSPIRE'` |
| `latitude` | `double precision` | Point on the footprint, not the centroid |
| `longitude` | `double precision` | |
| `municipality_id` | `text` | 5-digit INE code; text, because 56 begin with a zero. Kept for joins, never served |

`vulnerability` is deliberately **not** a column — it is computed per response
by `app/vulnerability.py`.

If the table is missing, the routes return **503** naming the table and columns
they looked for. Point `ASSET_SPECS_TABLE` / `LATITUDE_COLUMN` /
`LONGITUDE_COLUMN` elsewhere to read a different table. The bounding-box filter
is served by `asset_specs_lat_lon_idx`.

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
| `latitude`, `longitude` | `double precision` | A point guaranteed to be **inside** the forest. Named to match `asset_specs`, so the same bounding-box query serves both tables |
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
│   ├── queries.py               # the SELECTs, the INSERT, column introspection
│   ├── schemas.py               # response models
│   ├── vulnerability.py         # STUB: replace this with the real model
│   └── routers/
│       ├── assets.py            # GET /assets, the contract endpoint
│       ├── building_specs.py
│       └── add_building.py
├── db/
│   ├── init/
│   │   ├── 01_schema.sql        # protection schema, asset_specs, load_log
│   │   └── 02_forests.sql       # forest_areas
│   └── import/                  # loader staging area (gitignored)
├── data/
│   └── municipality_slug_map.csv
├── scripts/setup_db.sh          # one-time setup and data load
├── extract_buildings.py         # INSPIRE building GML  -> CSV
├── extract_forests.py           # INSPIRE forest GeoJSON -> CSV
└── tests/
    ├── test_assets.py
    ├── test_extract_forests.py
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

**Point assets.** Each municipality is streamed from
[datacloud.ide.cat](https://datacloud.ide.cat/geodades/inspire-edificis/)
straight into `extract_buildings.py` and loaded with `COPY` into
`protection.asset_specs`, so the 12 GB of source GML never touches the disk.
The insert and its `load_log` row share one transaction, making an interrupted
run resumable.

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
