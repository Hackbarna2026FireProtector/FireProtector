-- Public forests of Catalonia: the INSPIRE "Forest management areas" dataset
-- (theme AM, Area management/restriction/regulation zones), published by the
-- Departament d'Agricultura, Ramaderia, Pesca i Alimentació.
--
-- Idempotent, like 01_schema.sql: the container runs it on first boot and
-- setup_db.sh re-applies it on every run.

CREATE TABLE IF NOT EXISTS protection.forest_areas (
    -- INSPIRE localId, e.g. ID.AM.forest.231. Stable, so a reload matches
    -- rows up rather than duplicating them.
    forest_id           text PRIMARY KEY,
    name                text NOT NULL,
    -- Number in the Catàleg de Forests d'Utilitat Pública; null for the forests
    -- that are not catalogued (508 of 1,185). Text, not a number: the numbering
    -- restarts per province, so it repeats, and some carry a letter (56-B).
    cup_code            text,
    -- Number in the Elenc de forests de titularitat pública; null when none.
    elenc_code          text,
    -- Privately owned, but managed by the Generalitat under an agreement.
    has_agreement       boolean NOT NULL,
    -- Covered by an approved forest management plan.
    has_management_plan boolean NOT NULL,
    -- Certification scheme (only PEFC appears), null when uncertified.
    certification       text,
    area_ha             double precision NOT NULL,
    -- A point guaranteed to lie inside the forest. Named to match
    -- building_specs on purpose, so the same bounding-box query serves both.
    latitude            double precision NOT NULL,
    longitude           double precision NOT NULL,
    -- The forest's envelope: a cheap overlap test against a fire perimeter
    -- before anything loads the full geometry.
    min_latitude        double precision NOT NULL,
    max_latitude        double precision NOT NULL,
    min_longitude       double precision NOT NULL,
    max_longitude       double precision NOT NULL,
    -- INSPIRE versionId of the source feature, e.g. 20250714.
    version_id          text,
    -- GeoJSON MultiPolygon, ETRS89 geographic (EPSG:4258, within a metre of
    -- WGS84), lon/lat order -- ready for shapely.geometry.shape() or a map
    -- layer, without PostGIS. Roughly 17 kB per forest, so read it only when
    -- the exact boundary is needed.
    geometry            jsonb NOT NULL,
    -- Susceptibility to fire damage, 0-1 per the contract, random for now.
    -- Last on purpose: setup_db.sh COPYs this table with HEADER MATCH, so the
    -- column order here must equal extract_forests.py's FIELDS, and an
    -- ALTER ... ADD COLUMN on an existing table appends.
    vulnerability       double precision NOT NULL DEFAULT random() CHECK (vulnerability BETWEEN 0 AND 1)
);

-- Stated separately so a table created before this column existed picks it up.
ALTER TABLE protection.forest_areas
    ADD COLUMN IF NOT EXISTS vulnerability double precision NOT NULL DEFAULT random()
        CHECK (vulnerability BETWEEN 0 AND 1);

-- No secondary indexes on purpose: at 1,185 rows a full scan of everything but
-- the geometry is a fraction of a millisecond, and every one of them would
-- only slow the reload down.
