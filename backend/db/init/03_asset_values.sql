-- Real value and vulnerability for the asset register.
--
-- Until this ran, `value` was 1 on all 4.27M rows and `vulnerability` was
-- random() per row. Random is the more dangerous of the two: it varies per row,
-- so a ranking built on it looks sorted and a chart of it looks plausible,
-- while meaning nothing. Both are now assigned from the asset's type.
--
-- The numbers mirror app/data/asset_types.yaml, which the OSM critical-facility
-- provider reads at request time. They are duplicated rather than shared
-- because these two columns are *stored*: the API reads them as they sit, and
-- nothing recomputes them. Change one side and change the other, then re-run
-- this file.
--
-- Idempotent and cheap to re-run: the WHERE skips rows that already match, so
-- a second run updates nothing. The first run rewrites every row it touches,
-- which roughly doubles the table on disk until it is vacuumed -- the same
-- caveat 01_schema.sql documents for its own rewrites.

-- ---------------------------------------------------------------------------
-- Stop new rows arriving random.
--
-- The column default was random(), so every row inserted after the load --
-- including through POST /add_building -- kept arriving with a made-up
-- vulnerability. asset_type defaults to 'residential', so the two defaults now
-- agree: an insert that names no type gets the residential numbers.
-- ---------------------------------------------------------------------------
ALTER TABLE protection.asset_specs ALTER COLUMN vulnerability SET DEFAULT 0.7;
ALTER TABLE protection.asset_specs ALTER COLUMN value         SET DEFAULT 45;

-- ---------------------------------------------------------------------------
-- Assign both columns from the type, in a single pass over the table.
--
-- The first six types are every buildingNature code the Catalonia INSPIRE
-- register actually contains; the rest exist so a facility added by hand or
-- through POST /add_building lands on the same scale as the OSM ones.
-- ---------------------------------------------------------------------------
UPDATE protection.asset_specs AS a
   SET value         = t.value,
       vulnerability = t.vulnerability
  FROM (
    VALUES
      -- INSPIRE register types, weighted by hazard rather than replacement
      -- cost: a burning fuel or chemical tank endangers responders and spreads
      -- the fire, so it outranks the homes around it, and every home outranks
      -- every outbuilding.
      ('storageTank',   75.0, 0.9),
      ('tower',         60.0, 0.5),
      ('residential',   45.0, 0.7),
      ('greenhouse',    30.0, 0.8),
      ('shed',          15.0, 0.9),
      ('canopy',        10.0, 0.8),
      -- Critical facilities, matching the OSM side of the table.
      ('hospital',      95.0, 0.6),
      ('water_plant',   90.0, 0.5),
      ('care_home',     90.0, 0.8),
      ('substation',    85.0, 0.8),
      ('school',        80.0, 0.7),
      ('clinic',        70.0, 0.6),
      ('telecom_tower', 60.0, 0.7),
      ('fuel_station',  50.0, 0.9)
  ) AS t(asset_type, value, vulnerability)
 WHERE a.asset_type = t.asset_type
   AND (a.value         IS DISTINCT FROM t.value::numeric
     OR a.vulnerability IS DISTINCT FROM t.vulnerability::double precision);

-- Anything whose type is not listed above keeps the column defaults, which are
-- now the residential numbers rather than 1 and a random draw.
UPDATE protection.asset_specs
   SET value = 45, vulnerability = 0.7
 WHERE asset_type NOT IN (
    'storageTank', 'tower', 'residential', 'greenhouse', 'shed', 'canopy',
    'hospital', 'water_plant', 'care_home', 'substation', 'school', 'clinic',
    'telecom_tower', 'fuel_station'
   )
   AND (value = 1 OR vulnerability NOT IN (0.5, 0.6, 0.7, 0.8, 0.9));

-- protection.forest_areas is deliberately untouched. It carries the same two
-- columns, but /assets does not serve forests and the table is replaced
-- wholesale by every forest load, so values written here would not survive the
-- next setup_db.sh run. Put that logic in extract_forests.py instead.
