# FireProtector backend

Asset-register API for the wildfire values-at-risk tool. FastAPI over Postgres,
both in Docker. `GET /assets` implements a contract shared with other people's
code; the other two routes are internal.

Start with [Orientation](#orientation) and [Contract
invariants](#contract-invariants). The invariants are the part that fails
quietly.

---

## Orientation

**What is real:** the data. 4,269,286 point assets and 1,185 forest polygons,
both loaded from official INSPIRE sources, queryable by bounding box with
paging that works.

**What is not:** the scoring. Three fields are placeholders.

| Field | Loaded value | Where it comes from |
|---|---|---|
| `name` | `"residential"` for every loaded row | The INSPIRE building register carries no names at all — it is a register of footprints, not of named places |
| `value` | `1` for every loaded row | Column default. 1 means "not scored yet" |
| `vulnerability` | **A random number, 0–1, per row** | The `vulnerability` column's default, `random()` |

⚠️ **`vulnerability` is random, and random data looks exactly like real data.**
It varies per row, so a response will appear to rank assets and a chart of it
will look plausible. It means nothing. Do not treat any ordering derived from
it as a finding, and do not let it reach a demo as if it were a risk model
without saying so. See [Replacing the
placeholders](#replacing-the-placeholders).

**What the asset register is not:** a register of hospitals and substations.
It is the building footprint register, where 86% of rows have no type at all
and exactly **one** row in Catalonia is typed `hospital`. Real named
infrastructure arrives through `POST /add_building`, or by loading another
source. Do not assume `asset_type` is meaningful for most rows.

---

## Contract invariants

`GET /assets` is consumed by code we do not own. These rules are not style
preferences — breaking them produces wrong answers rather than errors.

1. **`bbox` is longitude-first**: `minLon,minLat,maxLon,maxLat`. This is the
   opposite order of the `lat`/`lon` parameters `/building_specs` takes. Swap
   them and the API returns a plausible, empty, wrong answer.
2. **`asset_id` must be unique within a response.** The consumer rejects the
   *entire response* on a duplicate, not just the offending feature. This is why
   ids are prefixed (`asset-<id>`, `forest-<localId>`) — the two tables have
   separate id spaces that would otherwise collide. Union in a third source and
   you must give it its own prefix.
3. **Paging must be totally ordered.** `ORDER BY wire_id` is what stops a page
   repeating or skipping rows under offset paging. Remove or weaken it and
   pagination silently loses assets — in a fire tool, assets in the fire's path.
4. **Every property is required.** `asset_id`, `asset_type`, `name`, `value`,
   `vulnerability`, `source` — a null in any of them makes the response invalid.
   This is why the columns are `NOT NULL` with defaults, and why `_clean_name`
   falls back to `"unnamed"` rather than returning nothing.
5. **Ranges are enforced**: `value` 1–100, `vulnerability` 0–1, `name` ≤ 120
   characters. `vulnerability` has a `CHECK` constraint holding it in range;
   `value` has none. The endpoint clamps and truncates on top of that, so one
   bad row cannot invalidate a whole page even if the table is swapped for one
   without the constraint.
6. **Errors are 400 or 500 only**, in the envelope
   `{"error": {"code", "message"}}`. FastAPI's native 422 is mapped to 400
   application-wide. This is why `/assets` takes every query parameter as a
   *string* and validates by hand — declaring `limit: int` would let FastAPI
   raise a 422 the contract does not define.
7. **`next` is the only signal that more data exists.** The contract has no
   `limit` parameter and no `truncated` flag, so a bare `?bbox=` request returns
   the first 1000 features and *looks complete*. Consumers must follow `next`.
   A 50 × 44 km box holds ~127,000 features — 127 pages.

`numberMatched`, `numberReturned` and `next` are additions beyond the contract.
They are legal because the contract's schema does not set
`additionalProperties: false`, and a consumer validating against it still passes.

---

## Endpoints

### `GET /assets` — the contract endpoint

GeoJSON `FeatureCollection` of everything in a bounding box: point assets from
`protection.asset_specs` and forest polygons from `protection.forest_areas`,
unioned into one response.

| Parameter | Required | Notes |
|---|---|---|
| `bbox` | yes | `minLon,minLat,maxLon,maxLat`, EPSG:4326. **Longitude first** |
| `limit` | no | Defaults to `ASSETS_PAGE_SIZE` (1000), which is also the ceiling |
| `offset` | no | Defaults to 0 |

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

Forests appear as `MultiPolygon` features with `asset_type: "forest"`, a real
name (`"FORESTS MUNICIPALS DE LLORET DE MAR"`), and constant `value: 1` /
`source: "INSPIRE"` — the forest table has no columns for either.

`asset_type` is an **open enum**. The contract lists `hospital`, `school`,
`substation` and so on, but our values are `residential`, `forest` and the
INSPIRE building natures (`shed`, `canopy`, `storageTank`, `greenhouse`,
`tower`). Consumers take their unknown-type path for effectively all of our
data, which the contract explicitly allows.

Ordering is lexical on the prefixed id, so **every point precedes every
forest**. That is a side effect of the ordering requirement, not a feature.

### `GET /building_specs` — internal

A centre and a radius rather than a box, which suits a map UI. Takes `lat`,
`lon`, `size_km`, optional `limit`; returns `{center, size_km, bounds, count,
limit, truncated, buildings[]}` where each row is the table as stored. Not part
of the contract, no forests, no `vulnerability`.

### `POST /add_building` — internal

The write path for real named assets. Body keys must be real columns; `latitude`
and `longitude` are required, everything else falls back to the column default.
`asset_id` is generated and cannot be supplied. **`source` defaults to
`INSPIRE`**, so pass your own (`"manual"`, `"osm"`) for anything that is not
from the register, or it will be labelled as official data.

Accepts a single object or a list (up to `MAX_INSERT_ROWS`). A batch is atomic.
The body is validated against the table's real columns read from the Postgres
catalog, so a typo returns a 400 naming the valid columns.

### `GET /health`

`{"status", "database", "detail"}`. **The container's `HEALTHCHECK` depends on
this route** — removing it breaks container health, and it is not in the
contract, so do not "tidy" it away.

### Errors

Every route, one envelope:

```json
{ "error": { "code": "bad_request", "message": "'bbox' minLon 1.6 is above maxLon 1.0." } }
```

| Status | `code` | When |
|---|---|---|
| 400 | `bad_request` | Missing/malformed `bbox`, bad `limit`/`offset`, bad column or coordinate in a POST body, constraint violation |
| 404 | `not_found` | Unknown path |
| 409 | `conflict` | Unique constraint violation (e.g. duplicate `source_id`) |
| 500 | `internal_error` | Unhandled. Logged in full, reported generically — an exception string can leak connection details |
| 503 | `unavailable` | Table missing or database unreachable |

Installed globally by `install_handlers()` in `app/errors.py`.

---

## Data model

Both tables are loaded from INSPIRE by `scripts/setup_db.sh`. No PostGIS.

### `protection.asset_specs` — 4,269,286 rows

| Column | Type | Notes |
|---|---|---|
| `asset_id` | `bigint` | Generated identity, primary key. Served as `asset-<id>` |
| `source_id` | `text` | INSPIRE localId, `ID.BU.<slug>.<uuid>`. **UNIQUE — this is the loader's upsert key.** Null for rows added via `/add_building` |
| `name` | `text` | `'residential'` for every loaded row |
| `asset_type` | `text` | INSPIRE building nature, `'residential'` for the 3,674,190 untyped rows |
| `value` | `numeric` | 1–100. Defaults to 1 |
| `vulnerability` | `double precision` | 0–1, `CHECK`ed. Defaults to `random()` — **currently random for every row** |
| `source` | `text` | Defaults to `'INSPIRE'` |
| `latitude`, `longitude` | `double precision` | Point on the footprint, not the centroid. Serves the bbox filter |
| `municipality_id` | `text` | 5-digit INE code. Text, because 56 Catalan municipalities have a leading zero. Kept for joins, never served |

Type distribution, for calibration: `residential` 3,674,190 · `shed` 483,998 ·
`canopy` 52,579 · `storageTank` 44,640 · `greenhouse` 8,303 · `tower` 5,575 ·
`hospital` 1.

### `protection.forest_areas` — 1,185 rows, 523,988 ha

The INSPIRE *Forest management areas* dataset (theme AM), published by the
Departament d'Agricultura, Ramaderia, Pesca i Alimentació under CC BY 4.0.

Key columns: `forest_id` (PK, `ID.AM.forest.<n>`), `name` (real names),
`cup_code`, `has_management_plan`, `area_ha`, `latitude`/`longitude` (a point
guaranteed *inside* the forest), the envelope `min_latitude`…`max_longitude`,
`geometry` (GeoJSON `MultiPolygon`, lon/lat, ~17 kB each) and `vulnerability`
(random, same as the assets — supplied by `extract_forests.py`, so it is
reshuffled every time the table is reloaded).

No index beyond the primary key: at 1,185 rows a scan of everything but the
geometry takes a fraction of a millisecond.

Envelope columns exist so a fire perimeter can be tested cheaply in SQL before
anything loads the polygons:

```sql
SELECT forest_id, name, geometry FROM protection.forest_areas
WHERE max_latitude  >= %(min_lat)s AND min_latitude  <= %(max_lat)s
  AND max_longitude >= %(min_lon)s AND min_longitude <= %(max_lon)s;
```

```python
from shapely.geometry import Point, shape
from shapely.prepared import prep

forest = prep(shape(row["geometry"]))      # jsonb arrives as a dict
at_risk = [a for a in assets if forest.covers(Point(a["longitude"], a["latitude"]))]
```

This is the **public forest estate**, not a fuel or vegetation map — the forests
the Generalitat manages, a fraction of Catalonia's forest cover. For continuous
land cover the same service publishes `inspire:LC.LandCoverSurfaces`.

---

## Replacing the placeholders

### Vulnerability

It is a **column**, filled with `random()`. Nothing computes it at request time —
there is no vulnerability module, and adding one would be a step backwards from
how this is now wired.

To replace the placeholder, write real numbers into the column:

```sql
UPDATE protection.asset_specs SET vulnerability = 0.9 WHERE asset_type = 'shed';
UPDATE protection.forest_areas SET vulnerability = ... ;
```

Both tables have the column and both are served from it. Two things to know
before you do:

- **`protection.forest_areas` is replaced wholesale on every forest load**, so
  hand-written values there are wiped by the next `setup_db.sh` run. Put the
  logic in `extract_forests.py` if it needs to survive.
- **The column default is `random()`**, so rows inserted later (including via
  `POST /add_building`) keep arriving with random values until that default is
  changed too.

### Value

`value` is a real column defaulting to 1. Score rows with `UPDATE`, or send them
through `POST /add_building` with a `value`. The endpoint clamps to 1–100.

### Real named assets

The register has none. Two routes in: `POST /add_building` for individual
records, or a new loader. The INSPIRE service already used here publishes
`US.Health` (5,489), `US.Education` (4,566), `US.SocialService` (4,562),
`US.PublicOrderAndSafety` (480) and `PF.ProductionFacility` (10,719) as named
points — `extract_forests.py` is the closest template. It does not publish
substations, telecom towers, water plants or fuel stations; those would come
from OSM.

---

## Verifying a change

Nothing here needs a database except the last two.

```bash
cd backend
.venv/bin/pytest -q                       # 80 tests, ~0.5s
```

```bash
# The contract, end to end
curl -s "http://localhost:5102/assets?bbox=2.78,41.69,2.84,41.74&limit=2" | python3 -m json.tool
# expect: numberMatched 13854, two Point features, next set

# Paging must not repeat rows
python3 -c "
import json, urllib.request
def ids(off):
    u = f'http://localhost:5102/assets?bbox=2.78,41.69,2.84,41.74&limit=50&offset={off}'
    return [f['properties']['asset_id'] for f in json.load(urllib.request.urlopen(u))['features']]
print('overlap:', len(set(ids(0)) & set(ids(50))))"        # expect: 0

# Error envelope
curl -s -w '\n%{http_code}\n' "http://localhost:5102/assets?bbox=nonsense"
# expect: {"error":{"code":"bad_request",...}} and 400
```

```bash
# The loader, without touching data: re-run the smallest municipality.
# ON CONFLICT (source_id) DO NOTHING means the row count must not move.
docker exec fireprotector-db psql -U fireprotector -d fireprotector -qtA \
  -c "DELETE FROM protection.load_log WHERE slug='lladurs'"
scripts/setup_db.sh --only lladurs --no-forests
```

---

## Loading the data

```bash
./backend/scripts/setup_db.sh                 # everything still missing
./backend/scripts/setup_db.sh --limit 10      # the 10 smallest pending
./backend/scripts/setup_db.sh --only olot     # named municipalities
./backend/scripts/setup_db.sh --workers 8     # parallelism (default 4)
./backend/scripts/setup_db.sh --forests-only  # refresh forests, skip assets
./backend/scripts/setup_db.sh --no-forests    # assets only
./backend/scripts/setup_db.sh --reset         # wipe the volume, start over
```

**Point assets.** Each municipality streams from
[datacloud.ide.cat](https://datacloud.ide.cat/geodades/inspire-edificis/)
straight into `extract_buildings.py` and is `COPY`d in, so the 12 GB of source
GML never touches disk. The insert and its `load_log` row share one transaction,
making an interrupted run resumable. 680 of Catalonia's 947 municipalities
publish building data, across 689 files (Barcelona is split by district).

**Forests.** One request to the INSPIRE OGC API - Features endpoint brings all
1,185 polygons as GeoJSON; the table is then replaced wholesale in one
transaction, so a re-run also drops forests the source no longer lists. ~10
seconds. GeoJSON rather than the ATOM/GML download because the GML carries only
the harmonised INSPIRE core, without the CUP number, management plan or
certification.

**Both loaders `COPY` with `HEADER MATCH`**, so Postgres checks the CSV header
against the staging columns. If you change a `FIELDS` list in an extractor, the
matching staging table in `setup_db.sh` (or `02_forests.sql`) must change too —
`HEADER MATCH` turns that into a loud error instead of silently loading values
into the wrong columns. A test asserts the forest one
(`test_fields_match_the_table_the_csv_is_copied_into`) — which is also why
`vulnerability` is the **last** column of `forest_areas`: `ALTER TABLE ... ADD
COLUMN` appends, so the CSV had to append too.

### If you change the schema

`db/init/*.sql` are applied **on every run** of `setup_db.sh`, in filename
order, and must stay idempotent. `01_schema.sql` contains a migration from the
original `building_specs` table guarded by `to_regclass(...) IS NULL → RETURN`,
written as a single `DO` block so it either completes or does nothing.

⚠️ **That migration rewrites a 4.27M-row table.** It is deliberately one
`ALTER TABLE` — the identity column forces a rewrite, so the `asset_type`
backfill rides along in the same pass rather than running as a separate
`UPDATE`. Split into two steps it needs ~3 GB of disk and WAL and *will fill a
laptop that is short of space* — this has already happened once and took the
database down. As written it runs in ~82 seconds for ~250 MB. Check free disk
before any migration that touches this table.

---

## Configuration

Environment or `.env` (see `.env.example`). `.env` is gitignored.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | Postgres connection string (required) |
| `ASSET_SPECS_TABLE` | `protection.asset_specs` | Point assets; `schema.table` accepted |
| `FOREST_AREAS_TABLE` | `protection.forest_areas` | Forest polygons unioned in by `/assets` |
| `LATITUDE_COLUMN` / `LONGITUDE_COLUMN` | `latitude` / `longitude` | Coordinate column names |
| `ASSETS_PAGE_SIZE` | `1000` | Page size for `/assets`; also its ceiling |
| `DEFAULT_LIMIT` / `MAX_LIMIT` | `500` / `10000` | Row caps for `/building_specs` |
| `MAX_INSERT_ROWS` | `1000` | Max rows per `POST /add_building` |
| `POOL_MIN_SIZE` / `POOL_MAX_SIZE` | `1` / `10` | Connection pool |
| `CORS_ORIGINS` | `["*"]` | Browser origins |
| `API_PORT` | `5102` | Host port in `docker-compose.yml`. **Fixed by the contract** |

---

## Design decisions, and why

Deliberate choices that look like omissions. Please read before "fixing" one.

### Why no PostGIS

The stack runs `postgres:18` with no spatial extension. Coordinates are numeric
columns, polygons are GeoJSON `jsonb`, bbox filtering is `BETWEEN`, and exact
geometry work happens in `shapely`.

Measured on this dataset: a ~10 km fire perimeter over the densest
wildland-urban interface in Catalonia takes **~135 ms end to end** — 42 ms to
pull 22,771 candidate buildings from 4.27M by index, 93 ms for point-in-polygon
on all of them. The entire forest layer is 1,185 polygons / ~20 MB, which loads
into memory in 800 ms and then answers intersection queries in 0.03 ms via an
`STRtree`.

PostGIS would buy `ST_Intersects` with a GiST index (moving polygon work into
SQL), exact geodesic distance, and `ST_AsMVT` for vector tiles. It costs an
image swap and a migration. **The decision is cheap to reverse** — the stored
GeoJSON is already valid input for `ST_GeomFromGeoJSON`, so adopting it later is
an `ALTER TABLE` plus an `UPDATE`, with no re-download and no re-parse. Revisit
if the ranking moves into SQL, or if a much larger polygon layer (land cover) is
loaded.

### Other choices

- **Surrogate `asset_id`, with `source_id` kept UNIQUE.** The generated key is
  what the contract wanted; the localId had to stay because it is the only thing
  that identifies a source record across reloads. Drop the unique constraint and
  a second load duplicates every row.
- **Forests unioned into `/assets` rather than served separately.** One call
  gives the decision layer everything in a box. Watch the consequence: forest
  geometry is ~17 kB against ~210 bytes for a point, so page sizes vary wildly.
- **`value`/`source` are constants for forests.** That table has no columns for
  them, and the forest loader replaces it wholesale on every run, so hand-set
  values there would be wiped.
- **`name` falls back to `'residential'`, not null.** The contract requires a
  name on every feature.
- **`vulnerability` is stored, not computed.** It was briefly a stubbed module
  called per feature; it is now a column on both tables, so every field the
  contract requires is read from the database rather than assembled in Python.
- **The API returns whole rows from the catalog** (`SELECT *`,
  `fetch_table_columns`), so adding a column does not require an API change.
- **Query parameters on `/assets` are strings.** See invariant 6.

---

## Layout

```
backend/
├── docker-compose.yml           # db (postgres:18) + api, API on :5102
├── Dockerfile                   # the API image; HEALTHCHECK hits /health
├── app/
│   ├── main.py                  # app factory, lifespan, CORS, /health
│   ├── config.py                # settings from env / .env
│   ├── db.py                    # async connection pool
│   ├── errors.py                # DB errors -> status codes; global envelope
│   ├── geo.py                   # centre+size_km -> box; parse_bbox
│   ├── payload.py               # POST body validation (pure functions)
│   ├── queries.py               # the SELECTs, the INSERT, introspection
│   ├── schemas.py               # response models, incl. the contract's
│   └── routers/
│       ├── assets.py            # GET /assets, the contract endpoint
│       ├── building_specs.py
│       └── add_building.py
├── db/
│   ├── init/
│   │   ├── 01_schema.sql        # protection schema, asset_specs, migration
│   │   └── 02_forests.sql       # forest_areas
│   └── import/                  # loader staging area (gitignored)
├── data/municipality_slug_map.csv
├── scripts/setup_db.sh          # containers + schema + both loads
├── extract_buildings.py         # INSPIRE building GML  -> CSV
├── extract_forests.py           # INSPIRE forest GeoJSON -> CSV
└── tests/
    ├── test_assets.py           # wire shape: names, ranges, parameters
    ├── test_extract_forests.py  # value cleanup, area maths, CSV/DDL match
    ├── test_geo.py              # box maths, bbox parsing
    └── test_payload.py          # what POST /add_building accepts
```

## Running the API on the host

Useful for a debugger; the database still comes from Docker.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # includes the loader deps
cp .env.example .env                            # already points at localhost
.venv/bin/uvicorn app.main:app --reload
```

`app/` is mounted into the container with `--reload`, so edits take effect
without a rebuild. Rebuild only when `requirements.txt` changes:
`docker compose up -d --build api`.
