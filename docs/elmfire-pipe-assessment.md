# ELMFIRE pipeline assessment

Living document for `backend/fire_spread/`: what ELMFIRE takes, what we feed it, how good each
piece is, and what the hindcast says. Update the **Status** table and the **Hindcast log** when
something changes; keep the rest short. Namelist names are verbatim; "ours" is what the pipeline
writes into `elmfire.data` (see `fire_spread/elmfire_config.py`).

_Last updated 2026-09-20 · ELMFIRE main @ `cbf924a` · tier 50 m._

## 1. Inputs

Grades: **good** fit for purpose · **ok** usable, known bias · **weak** dominant error source.

| Input | ELMFIRE expects | We feed | Grade | Notes |
|---|---|---|---|---|
| `FBFM` fuel model | S&B 40 / Anderson 13 codes | ZAFM-DW 2026 (10 m → 50 m mode); DARP scars < 2 y → NB9, 2–6 y → GR2 | **weak** | Global Dynamic-World product, not field-validated. SH7 (chaparral) dominant shrub class; GR4 = *all* agriculture incl. irrigated orchards; 33 % of "shrub" cells have LiDAR canopy ≥ 40 %. |
| `DEM/SLP/ASP` | m, deg, deg | Copernicus GLO-30 → gdaldem | ok | Surface model: slope inflated at forest edges. ICGC 2 m DTM → fix + 30 m tier. |
| `CC/CH/CBH/CBD` | %, m×10, m×10, kg m⁻³×100 | ICGC/CREAF LiDAR 2016–17 | ok | Cover/height measured. CBH = 0.4·HM, CBD = biomass/(HM−CBH) are heuristics; 9–10 y old. |
| `ADJ` spread multiplier | Float32 | `ADJ_FACTOR` (default 1.0), uniform | ok | Primary calibration surface; global scalar only so far. |
| `PHI` initial fire | < 0 burning | 1.0 (CSV ignition) | good | Perimeter ignition is one raster away. |
| `BARRIER` | width m | OSM roads + waterways by class | ok | Class-average widths; field margins / firebreak strips missing. |
| `WS/WD` | 20 ft mph (10 m accepted) | Open-Meteo best_match (AROME 1.3 km) 4×4 grid + ICON-EU-EPS members | **weak** | Not terrain-adjusted: no channelling / ridge speed-up (WindNinja). |
| `M1/M10/M100` | % | Simard EMC + 1/10/100 h lag, 48 h spin-up, rain | ok | No aspect/solar term. |
| `LH/LW/FMC` live | % | monthly Catalan climatology | ok | Coarse; satellite LFMC or GRAF sampling via rasters. |
| `FUEL_MODEL_FILE` | Rothermel table | `scott_burgan` (default) / `mediterranean` (provisional) | ok | Mediterranean set is literature-range, uncalibrated. |
| `IGNITIONS_CSV` | case, band, x, y | one row per case on its own NWP block | good | Only path giving per-case weather. |
| Pyromes, assets, SDI, WUI rasters | — | unused | — | ZHR zones ready as pyromes. |

## 2. Knobs (ELMFIRE default → ours)

**INPUTS** `DT_METEOROLOGY` 3600 · `WS_AT_10M` T · `DEAD_MC_IN_PERCENT` T · canopy unit switches T ·
`USE_BARRIERS` T if `barrier.tif` · `SURFACE_SPREAD_MODEL` ROTHERMEL · live moisture constant.

**TIME_CONTROL** `SIMULATION_TSTART` = minute offset into the ignition hour, `TSTOP` = +duration ·
`DT/DTMAX/CFL` 5/300/0.4 · `USE_DIURNAL_ADJUSTMENT_FACTOR` T, `OVERNIGHT_ADJUSTMENT_FACTOR` 0.4
(default 0.1), burn period 10 h / 0.667 · `FORECAST_START_HOUR`, `CURRENT_YEAR`, `HOUR_OF_YEAR` real
(UTC; sunrise/sunset computed by ELMFIRE at the domain corner).

**SIMULATOR** `NUM_IGNITIONS` 0 (CSV path) · `CROWN_FIRE_MODEL` 1 (Cruz), `CRITICAL_CANOPY_COVER`
0.39, `CROWN_RATIO` 1.0, `MAX_LOW` 8 (env) · `WIND_FLUCTUATIONS` T, speed 0.2, direction 0.1
(**fraction of 360°**, ±18°; docs wrongly say degrees), every 30 s · `WX_BILINEAR_INTERPOLATION` T
(grid padded past the NaN corner) · `MAX_RUNTIME` = timeout − 30 s · defaults: `PHIW_ADJ`,
`PHIS_ADJ`, `WSMFEFF_LOW_MULT`, `CROWN_FIRE_ADJ`, `CROWN_FIRE_SPREAD_RATE_LIMIT`, `BANDTHICKNESS`.

**MONTE_CARLO** `RANDOM_IGNITIONS` + `CSV_FIXED_IGNITION_LOCATIONS` T · `NUM_ENSEMBLE_MEMBERS` =
cases · `NUM_METEOROLOGY_TIMES` = bands per block (**1 freezes weather at band 1**) ·
`METEOROLOGY_BAND_START/STOP/SKIP_INTERVAL` = 1 / last block / block length · `SEED` from request ·
perturbations: `M1` GAUSSIAN σ 1.5 %, `ADJ` UNIFORM −0.2..+0.25, plus `WS`/`WD` GAUSSIAN σ from the
NWP spread only when no ensemble members are available.

**SPOTTING** off by default; `?spotting=1` → `PER-MW` generation, `EMPIRICAL` (Sardoy) distance,
`EULERIAN` accumulation, `DIRECT` ignition `PIGN` 100, crown 2 %, surface 0.5 % above 1000 kW/m.

**SUPPRESSION / WUI / CALIBRATION / SMOKE** unused. Grids are free-burning, no suppression, urban
cells are walls; pyrome tables empty.

**OUTPUTS** `DUMP_TIME_OF_ARRIVAL` only; flame length / intensity rasters off.

## 3. Strengths

- Real NWP ensemble member per case (wind, T, RH, rain co-vary) — the only code path that allows it.
- Weather advances hour by hour (frozen-band bug fixed); ignition minute honoured; lagged fuel
  moisture with 48 h history and rain.
- 4×4 spatial weather grid; OSM fire breaks (−⅓ area on the reference fire; upstream MPI bug patched).
- Night damping; burn-scar fuel remap; LiDAR canopy; monthly live/foliar moisture.
- Uncertainty from distinct members + model-error perturbations; reproducible seed; every run is an
  inspectable directory; 63 unit + 6 real-ELMFIRE tests.
- Every knob checked against the Fortran; five doc errors caught (fluctuation units, sunrise inputs,
  band semantics, bilinear corner, perturbation units).

## 4. Flaws, ranked by expected impact

1. **No calibration** — `ADJ = 1`, pyrome tables empty. First hindcast (18 fires): Jaccard 0.16–0.18, median area bias 2.8–4.6× — over-prediction is suppression-shaped, so calibrate on free-burning cases or add the extended-attack model first.
2. **Fuel map** — ZAFM-DW classes (see §1). Real fix: Catalan land-cover crosswalk (MCSC / Mapa Forestal).
3. **Wind not terrain-adjusted** — WindNinja downscaling.
4. **Spotting off by default**, untested on real fires.
5. **50 m cells on a DSM slope** — `--res 30` exists; needs a real DTM.
6. Live/foliar moisture monthly table; canopy CBH/CBD heuristics (2016–17).
7. ICON-EU-EPS lacks humidity (members share deterministic RH).
8. Night ignitions above the moisture of extinction end at t 0 (model behaviour; must be explained).
9. No suppression, no WUI spread (must be labelled).
10. Only arrival time output (flame length / intensity one flag away).

## 5. Status

| Item | State | Since |
|---|---|---|
| Hindcast loop (`scripts/fire_spread/hindcast.py`) | built; DARP perimeters, ERA5 archive weather, Jaccard/Sørensen/bias | 2026-09-20 |
| Global `ADJ` calibration | blocked: bias is suppression-dominated; needs free-burning subset or extended-attack model first | 2026-09-20 |
| Pyrome × fuel tables | not started | |
| Fuel set decision (`scott_burgan` vs `mediterranean`) | first batch favours `mediterranean` (J 0.177 vs 0.155, bias 2.8 vs 4.6); default unchanged pending a suppression-aware rerun | 2026-09-20 |
| WindNinja | not started | |
| Catalan fuel map crosswalk | not started | |
| Spotting validation | not started | |
| Satellite LFMC / ICGC DTM | not started | |

Hindcast caveats: DARP gives perimeter, date and municipality only — no ignition point, time or
duration. The loop places the ignition at the most upwind cell of the perimeter (mean ERA5 wind
over the fire afternoon), ignites at 12:00 UTC, runs 24 h (`--hours`) and scores against the final
perimeter, so multi-day fires read as under-prediction. FIRMS hotspots would give real ignition
points and timing.

## 6. Hindcast log

| Date | Cases | Settings | Jaccard mean/median | Sørensen | Area bias median (p25–p75) | Notes |
|---|---|---|---|---|---|---|
| 2026-09-20 | 18 (2019–2024, ≥100 ha; 2 skipped at the coverage edge) | `scott_burgan_adj1_h24`, 4 members, pmin 0.5, barriers on | 0.155 / 0.150 | 0.252 | 4.62 (0.77–5.87) | ERA5 weather, 24 h, no suppression |
| 2026-09-20 | same 18 | `mediterranean_adj1_h24` | **0.177** / 0.138 | **0.278** | **2.82** (0.56–6.52) | better on 11/18 fires; on par with CloudFire's CONUS mean |

Per-fire results: `backend/data/fire_spread/hindcast/<tag>.csv`, log in `batch.log`.

What the first batch says:

- **Over-prediction dominates** (median bias 2.8–4.6): most 100–500 ha fires were contained
  by Bombers within hours; the model burns freely for 24 h. Do **not** tune `ADJ` on this bias —
  it would be compensating for suppression, not spread rate. Calibrate on the free-burning
  fires (Artesa de Segre 2022: bias 0.97–1.05, J 0.40–0.42; Castellar de la Ribera: J 0.53
  Mediterranean) and on the first hours of the large ones, or add the extended-attack model.
- **Two catastrophic over-predictions** — Ciutadilla 2024 (234 ha → 43 000 ha S&B, 10 800 ha
  Mediterranean) and Cabacés 2024 (36×): both in the Lleida/Priorat cereal mosaic in July/September,
  where ZAFM's GR4 "agriculture" burns as continuous cured grass. This is the fuel-map flaw (§4.2)
  measured; harvested/irrigated agriculture needs an NB or seasonal class.
- **Under-prediction of the big multi-day fires** as expected at 24 h (Ribera d'Ebre 2019: 0.43–0.55).
  El Pont de Vilomara 2022 (1580 ha in one afternoon) at 0.01–0.09 is not explained by duration:
  ignition placement or ERA5 wind (real fire was driven by a local W-NW wind and spotting)
  — a case for WindNinja + spotting.
- **Mediterranean fuel set** lowers bias and raises Jaccard on average without a hindcast-fitted
  parameter; keep it provisional but it is now the better-supported default candidate.
- Winter/spring fires (Roses Feb 2022, Portbou Apr 2023, Naut Aran Jan 2019: bias 3–7) run on
  the July-style live-moisture table only through the month lookup; Tramuntana fires spot.

Reference for expectations: CloudFire's CONUS validation (WildfireAV) reports mean Jaccard 0.178,
Sørensen 0.278 for ELMFIRE (FARSITE 0.176 / 0.274).
