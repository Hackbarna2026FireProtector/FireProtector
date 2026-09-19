-- Schema for the FireProtector asset register.
-- Idempotent: the container runs this on first boot, and setup_db.sh re-applies
-- it on every run so an existing volume picks up changes too.

CREATE SCHEMA IF NOT EXISTS protection;

-- ---------------------------------------------------------------------------
-- Migration from the original building register.
--
-- The table began as protection.building_specs, keyed on the INSPIRE localId,
-- and became the asset register when the API adopted the /assets contract.
-- It is migrated in place rather than reloaded: the 4.27M rows in it cost
-- about 11 minutes to fetch and parse again.
--
-- One statement, so it either completes or does nothing.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('protection.building_specs') IS NULL THEN
        RETURN;
    END IF;

    -- Dropped before the rewrite and recreated under their new names further
    -- down, so roughly 630 MB of index is not dragged through it.
    DROP INDEX IF EXISTS protection.building_specs_lat_lon_idx;
    DROP INDEX IF EXISTS protection.building_specs_municipality_idx;
    ALTER TABLE protection.building_specs DROP CONSTRAINT IF EXISTS building_specs_pkey;

    ALTER TABLE protection.building_specs RENAME TO asset_specs;
    -- The localId stops being the key and becomes provenance.
    ALTER TABLE protection.asset_specs RENAME COLUMN building TO source_id;
    ALTER TABLE protection.asset_specs RENAME COLUMN building_type TO asset_type;

    -- Deliberately one ALTER TABLE. The identity column forces a full rewrite
    -- of 4.27M rows, so the asset_type backfill rides along in the same pass
    -- rather than running as a separate UPDATE that would write the whole
    -- table a second time -- which needs about 3 GB of disk and WAL between
    -- them, and will fill a laptop that is short of space.
    ALTER TABLE protection.asset_specs
        ALTER COLUMN asset_type TYPE text USING coalesce(asset_type, 'residential'),
        ALTER COLUMN asset_type SET NOT NULL,
        ALTER COLUMN asset_type SET DEFAULT 'residential',
        ADD COLUMN asset_id bigint  GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        ADD COLUMN name     text    NOT NULL DEFAULT 'residential',
        ADD COLUMN value    numeric NOT NULL DEFAULT 1,
        ADD COLUMN source   text    NOT NULL DEFAULT 'INSPIRE';

    ALTER TABLE protection.asset_specs
        ADD CONSTRAINT asset_specs_source_id_key UNIQUE (source_id);
END $$;

-- One row per asset. On a fresh database this is the whole story; on a
-- migrated one it is a no-op, and the column order differs from the listing
-- below because the migration appended its new columns.
CREATE TABLE IF NOT EXISTS protection.asset_specs (
    -- Surrogate key. Served as "asset-<id>", since the contract types
    -- asset_id as a string and /assets unions this table with the forests.
    asset_id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- INSPIRE localId, e.g. ID.BU.abella-conca.<uuid>. Unique, so the loader
    -- can upsert on it and a re-run cannot duplicate a municipality. Null for
    -- assets added through POST /add_building.
    source_id       text UNIQUE,
    -- The source register has no names at all, so loaded rows say
    -- 'residential'; a real name arrives only with a hand-added asset.
    name            text    NOT NULL DEFAULT 'residential',
    -- INSPIRE buildingNature (shed, storageTank, tower, ...), 'residential'
    -- where the source gives none. Not the contract's enum, which is open.
    asset_type      text    NOT NULL DEFAULT 'residential',
    -- Relative importance, 1-100 per the contract. 1 means "not scored yet".
    value           numeric NOT NULL DEFAULT 1,
    -- Susceptibility to fire damage, 0-1 per the contract. Currently a random
    -- number per row: a placeholder with the right shape, not a risk model.
    -- The CHECK is what guarantees the contract's range at the data layer.
    vulnerability   double precision NOT NULL DEFAULT random() CHECK (vulnerability BETWEEN 0 AND 1),
    -- Provenance. The loader's rows are INSPIRE; callers may override it.
    source          text    NOT NULL DEFAULT 'INSPIRE',
    -- Point on the footprint, not the centroid. Serves the bbox filter.
    latitude        double precision NOT NULL,
    longitude       double precision NOT NULL,
    -- 5-digit INE code, kept for joins and rollups; never served by /assets.
    -- Text, because 56 Catalan municipalities have a leading zero.
    municipality_id text
);

-- Susceptibility to fire damage. Stated separately so a table created before
-- this column existed picks it up.
--
-- ADD COLUMN with a *volatile* default is what fills it: Postgres rewrites the
-- table once and evaluates random() per row. A nullable ADD COLUMN followed by
-- an UPDATE would be metadata-only and then write every row a second time,
-- leaving the table bloated to roughly twice its size until vacuum.
ALTER TABLE protection.asset_specs
    ADD COLUMN IF NOT EXISTS vulnerability double precision NOT NULL DEFAULT random()
        CHECK (vulnerability BETWEEN 0 AND 1);

-- Neither is known for an asset added through POST /add_building, so neither
-- may be NOT NULL. Stated separately because a migrated table inherits NOT NULL
-- on both from the original building register, where every row had them.
ALTER TABLE protection.asset_specs ALTER COLUMN source_id       DROP NOT NULL;
ALTER TABLE protection.asset_specs ALTER COLUMN municipality_id DROP NOT NULL;

-- Serves the bounding-box filter in GET /assets and GET /building_specs.
CREATE INDEX IF NOT EXISTS asset_specs_lat_lon_idx
    ON protection.asset_specs (latitude, longitude);

CREATE INDEX IF NOT EXISTS asset_specs_municipality_idx
    ON protection.asset_specs (municipality_id);

-- Which municipalities have been loaded, so the load is resumable: a re-run
-- skips what is already in, and an interrupted municipality is simply redone.
CREATE TABLE IF NOT EXISTS protection.load_log (
    slug      text PRIMARY KEY,
    n_rows    bigint      NOT NULL,
    gml_bytes bigint,
    loaded_at timestamptz NOT NULL DEFAULT now()
);
