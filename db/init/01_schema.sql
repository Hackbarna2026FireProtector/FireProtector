-- Schema for the FireProtector building register.
-- Idempotent: the container runs this on first boot, and setup_db.sh re-applies
-- it on every run so an existing volume picks up changes too.

CREATE SCHEMA IF NOT EXISTS protection;

-- One row per INSPIRE building. Columns mirror extract_buildings.py, except
-- location_lat/location_long, which are stored as latitude/longitude so the
-- backend's defaults work unchanged.
CREATE TABLE IF NOT EXISTS protection.building_specs (
    -- INSPIRE localId, e.g. ID.BU.abella-conca.<uuid>. Stable and unique,
    -- so re-loading a municipality cannot duplicate its buildings.
    building        text PRIMARY KEY,
    building_type   text,
    latitude        double precision NOT NULL,
    longitude       double precision NOT NULL,
    -- 5-digit INE code. Text, because 56 Catalan municipalities have a
    -- leading zero (Badalona is 08015, not 8015).
    municipality_id text NOT NULL
);

-- Serves the bounding-box filter in GET /building_specs.
CREATE INDEX IF NOT EXISTS building_specs_lat_lon_idx
    ON protection.building_specs (latitude, longitude);

CREATE INDEX IF NOT EXISTS building_specs_municipality_idx
    ON protection.building_specs (municipality_id);

-- Which municipalities have been loaded, so the load is resumable: a re-run
-- skips what is already in, and an interrupted municipality is simply redone.
CREATE TABLE IF NOT EXISTS protection.load_log (
    slug      text PRIMARY KEY,
    n_rows    bigint      NOT NULL,
    gml_bytes bigint,
    loaded_at timestamptz NOT NULL DEFAULT now()
);
