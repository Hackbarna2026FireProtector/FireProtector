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
-- One statement, so it either completes or does nothing. The order is chosen
-- to keep the peak disk use low on a developer laptop: the large indexes are
-- dropped before the rewrite and rebuilt afterwards, and the UPDATE runs
-- before the rewrite that compacts what it leaves behind.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('protection.building_specs') IS NULL THEN
        RETURN;
    END IF;

    DROP INDEX IF EXISTS protection.building_specs_lat_lon_idx;
    DROP INDEX IF EXISTS protection.building_specs_municipality_idx;

    ALTER TABLE protection.building_specs RENAME TO asset_specs;
    -- The localId stops being the key and becomes provenance.
    ALTER TABLE protection.asset_specs RENAME COLUMN building TO source_id;
    ALTER TABLE protection.asset_specs RENAME COLUMN building_type TO asset_type;

    -- Constant defaults, so these are metadata-only and do not rewrite 4.27M rows.
    ALTER TABLE protection.asset_specs
        ADD COLUMN name   text    NOT NULL DEFAULT 'residential',
        ADD COLUMN value  numeric NOT NULL DEFAULT 1,
        ADD COLUMN source text    NOT NULL DEFAULT 'INSPIRE';

    -- The INSPIRE GML gives no buildingNature for 86% of buildings.
    UPDATE protection.asset_specs SET asset_type = 'residential' WHERE asset_type IS NULL;
    ALTER TABLE protection.asset_specs
        ALTER COLUMN asset_type SET DEFAULT 'residential',
        ALTER COLUMN asset_type SET NOT NULL;

    -- Dropping the old primary key first means its index is not carried
    -- through the rewrite that the identity column forces.
    ALTER TABLE protection.asset_specs DROP CONSTRAINT building_specs_pkey;
    ALTER TABLE protection.asset_specs
        ADD COLUMN asset_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY;
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
    -- Provenance. The loader's rows are INSPIRE; callers may override it.
    source          text    NOT NULL DEFAULT 'INSPIRE',
    -- Point on the footprint, not the centroid. Serves the bbox filter.
    latitude        double precision NOT NULL,
    longitude       double precision NOT NULL,
    -- 5-digit INE code, kept for joins and rollups; never served by /assets.
    -- Text, because 56 Catalan municipalities have a leading zero.
    municipality_id text
);

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
