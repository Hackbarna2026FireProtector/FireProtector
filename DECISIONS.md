# DECISIONS

One line per decision: what, why, how to change it. Vocabulary lives in
[CONTEXT.md](CONTEXT.md); this file is for choices that a reasonable reader
would otherwise want to undo.

## The decision layer

- **Ported into this FastAPI app rather than run beside it.** The decision
  layer was a separate Flask service calling this one over HTTP. Its engine is
  pure functions over dataclasses, so it moved in whole and the network hop,
  the provider-selection layer and a second process all went away. Change:
  `backend/app/engine/`, `backend/app/briefing/` are the ported trees.
- **Mounted under `/api`, never at the root.** The root implements the
  asset-register contract other people's code is written against; `/api` serves
  one front end and changes with it. Keeping them apart is what makes it safe
  to change one. Change: `app/main.py`.
- **A "fire" here is a hypothetical ignition, not a detected incident.** The
  contract's `Fire` carried `detected_at` and `status: active`; nothing in this
  system detects anything, so both were fiction and both are gone. The wire
  concept is a *scenario*. Change: `app/decision/scenarios.py`, `CONTEXT.md`.
- **Scenarios come from a seed file, not a table.** `app/data/scenarios.json`,
  read at startup. A handful of coordinates does not need a schema, and the
  file is reviewable in a diff. Change: edit the file; a `protection.scenarios`
  table and a map click to drop an ignition are the natural next steps.
- **`GET /api/.../hotspots` was removed, not reimplemented.** Deepfire hotspots
  belong to a detected fire's cluster. A hypothetical ignition has none, so the
  endpoint could only ever have returned `[]`. Change: it is not coming back
  unless scenarios can be seeded from real clusters.

## Spread and confidence

- **Hourly perimeters feed both the map and the scoring; the arrival grid is
  derived.** Deepfire returns one perimeter per simulated hour, which *is* an
  arrival contour (`eta_minutes = hour × 60`). The 100 m raster that
  `/fire/arrival-grid` serves is built from those same perimeters, so scoring
  reads the polygons directly: sampling the raster would quantise every ETA to
  a whole hour and collapse `exp(-eta/tau)` into a handful of ties. Change:
  `app/decision/spread.py`.
- **`ensembleMembers=10`, and `burn_probability` is `confidence`.** Verified
  live on 2026-09-20: a 24-hour run returns 151 perimeters — an hourly core at
  probability 1.0 plus disjoint fringes down to 0.1. That is a real, measured
  confidence signal, and an asset inside a 0.1 fringe genuinely is a less
  certain casualty than one inside the core. **The alternative that was
  rejected**: the decision layer's own fallback invented confidence as
  `0.9 − 0.05 × hour`, a monotone function of arrival time — which is what
  `f_urgency` already is, so it would have added a fourth slider controlling
  the third one's variable. (Its probability lookup never fired: it read
  `probability`/`arrival_probability`, and the field is called
  `burn_probability`.) Change: `fire_spread/deepfire.py::ENSEMBLE_MEMBERS`.
- **`run_simulation` returns only the certain core.** `build_arrival_grid`
  assumes perimeters nest — hour *h* contains hour *h−1* — and a fringe
  polygon does not. Handing it the fringes would silently mark cells as reached
  that the forecast does not reach. `run_simulation_detailed` is the one that
  keeps probabilities. Change: `fire_spread/deepfire.py`.
- **Invalid perimeters are repaired, then dropped.** 54 of 151 perimeters in a
  live run were invalid (degenerate rings, ring self-intersections) and on one
  of them `make_valid` itself raised `Overlay input is mixed-dimension`;
  `buffer(0)` fixed that one. Both are tried, non-areal parts are discarded,
  and what survives neither is dropped with a warning — losing 150 good
  perimeters to one sliver would lose the forecast. Change:
  `app/decision/spread.py::clean_perimeter`.
- **`DURATION_HOURS` stays 24.** Known consequence: with `tau = 90` minutes the
  nearest asset in a 24-hour burn typically arrives around hour 5, so
  `f_urgency ≈ 0.04` and no asset clears the `critical` floor in two of the
  three seeded scenarios. Either the horizon comes down to ~6 hours or `tau`
  goes up; 6 hours is the decision layer's own default and closer to an
  operational window. Change: `fire_spread/deepfire.py::DURATION_HOURS`.

## What gets scored

- **Only what the fire reaches**, contours plus a 1 km margin. Not an
  optimisation: an asset outside the outermost contour has no arrival time, so
  its risk is exactly 0. Scoring the surrounding region would add six figures
  of guaranteed-zero rows to every response and to all thirteen sensitivity
  passes. Change: `REACHED_MARGIN_M`.
- **Unpaged, unlike `GET /assets`.** That endpoint pages because it is public
  with an unbounded box. This query is bounded by a burn perimeter, and a
  caller that stopped at the first page would rank a thousand arbitrary
  buildings and present them as the whole picture. Change:
  `app/decision/assets.py`.
- **`value` and `vulnerability` come from `asset_type`, weighted by hazard.**
  A burning fuel or chemical tank endangers responders and spreads the fire, so
  `storageTank` (75) outranks `residential` (45), and every home outranks every
  outbuilding. The register's only types are `shed`, `canopy`, `storageTank`,
  `greenhouse`, `tower` and the untyped `residential` bulk — there are no
  hospitals in it. Change: `app/data/asset_types.yaml` **and**
  `db/init/03_asset_values.sql`; the register's columns are stored, not
  computed, so both sides must move together.
- **`vulnerability`'s column default is no longer `random()`.** It was, which
  meant every row inserted after the load arrived with a made-up number that
  varied per row — a ranking built on it looks sorted and means nothing.
  Change: `db/init/03_asset_values.sql`.
- **Named assets come from OpenStreetMap, live, per scenario.** The register
  has no names at all. This is the one hard third-party dependency at demo
  time, and its failure is reported in `/api/.../score` as `named_layer` rather
  than swallowed. Only planet-wide mirrors are listed: a regional mirror
  answers with HTTP 200 and zero results, which cannot be told apart from an
  honest empty answer. Change:
  `app/providers/osm_assets.py::DEFAULT_ENDPOINTS`, `OVERPASS_URLS`.

## Runtime

- **Bundles are recorded to disk as the payloads they arrived as.** A bundle is
  a forecast plus a reached set; building one costs a Deepfire simulation of
  two to four minutes. They are stored as EPSG:4326 GeoJSON rather than pickled
  geometries so they survive library upgrades and stay reviewable, and exposure
  is recomputed on load because it is cheap next to a simulation. Committing
  them is what makes the UI demonstrable with no credentials. Change:
  `app/decision/bundle.py`; delete a file under `data/bundles/` to resimulate.
- **Scoring runs in the threadpool.** Sensitivity re-scores the whole reached
  set thirteen times — measured at 1.9 s to 5.3 s for 3,200–7,800 assets — and
  the UI fires it on every slider change. On the event loop that would stall
  every other request. Change: `app/routers/decision.py`.
- **One lock per scenario.** Deepfire allows two simulations in flight for the
  whole client, so two browser tabs on one scenario must not queue two runs.
  Change: `app/decision/bundle.py::get_bundle`.
- **`numpy` pinned down to 2.3.4** to match what the ported engine was
  developed against. Nothing here needed 2.5.3. Change: `requirements.txt`.
