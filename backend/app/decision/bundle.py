"""Per-scenario bundles: the expensive half of the decision layer, cached.

A bundle is everything derived from one ignition scenario that costs real time
to produce — the spread forecast, the reached set, and the exposure join
between them. Scoring, sensitivity and briefing all read from it and none of
them changes it, which is why they share one.

Building a bundle costs a Deepfire simulation (tens of seconds, capped at two
in flight) plus an Overpass query. Both are recorded to disk as the contract
payloads they arrived as, so a restart reloads instead of resimulating, and a
bundle committed to the repository makes the whole app demonstrable with no
Deepfire credentials at all.

What is persisted is deliberately the *inputs* — forecast and assets as
EPSG:4326 GeoJSON — rather than the derived exposure. Exposure is cheap next to
a simulation, JSON survives library upgrades in a way pickled shapely
geometries do not, and a recorded bundle stays reviewable in a diff.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyproj
from psycopg_pool import AsyncConnectionPool
from shapely.ops import transform

from app.config import Settings
from app.decision.assets import facilities_in_area, reached_area, register_assets_in_area
from app.decision.scenarios import Scenario
from app.decision.spread import perimeters_to_payload
from app.decision_config import DATA_ROOT
from app.engine.contracts import Asset, SpreadForecast, parse_assets, parse_spread
from app.engine.exposure import AssetExposure, compute_exposure
from app.providers.osm_assets import OsmAssetProvider

log = logging.getLogger(__name__)

BUNDLE_DIR = DATA_ROOT / "bundles"
BUNDLE_VERSION = 1

_bundles: dict[str, "Bundle"] = {}
_locks: dict[str, asyncio.Lock] = {}


class BundleUnavailable(RuntimeError):
    """No bundle on disk and it could not be built (no credentials, or upstream down)."""


@dataclass(frozen=True)
class Bundle:
    """One scenario's forecast, reached set and exposure."""

    scenario: Scenario
    forecast: SpreadForecast
    assets: list[Asset]
    exposures: list[AssetExposure]
    built_at: datetime
    from_disk: bool
    # Why the named layer is missing, if it is. None means Overpass answered.
    facilities_error: str | None = None

    @property
    def named_assets(self) -> list[Asset]:
        """Critical facilities: the only assets that carry a real name."""
        return [a for a in self.assets if a.source != "INSPIRE"]


# ----------------------------------------------------------------- on disk --


def _path(scenario_id: str) -> Path:
    return BUNDLE_DIR / f"{scenario_id}.json"


def _write(
    scenario: Scenario,
    spread_payload: dict,
    assets_payload: dict,
    facilities_error: str | None,
) -> None:
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    path = _path(scenario.scenario_id)
    path.write_text(
        json.dumps(
            {
                "version": BUNDLE_VERSION,
                "scenario_id": scenario.scenario_id,
                "recorded_at": datetime.now(UTC).isoformat(),
                "facilities_error": facilities_error,
                "spread": spread_payload,
                "assets": assets_payload,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("recorded bundle %s (%d bytes)", scenario.scenario_id, path.stat().st_size)


def _read(scenario: Scenario) -> Bundle | None:
    """Rebuild a bundle from its recorded payloads, or None if there is none."""
    path = _path(scenario.scenario_id)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("version") != BUNDLE_VERSION:
            log.warning("bundle %s is version %s, ignoring", scenario.scenario_id, raw.get("version"))
            return None
        forecast = parse_spread(raw["spread"])
        assets = parse_assets(raw["assets"])
    except Exception:
        log.warning("could not read bundle %s", scenario.scenario_id, exc_info=True)
        return None

    return Bundle(
        scenario=scenario,
        forecast=forecast,
        assets=assets,
        exposures=compute_exposure(forecast, assets, scenario.as_engine_fire().ignition_point),
        built_at=datetime.fromisoformat(raw["recorded_at"]),
        from_disk=True,
        facilities_error=raw.get("facilities_error"),
    )


# ----------------------------------------------------------------- build ----


async def _build(
    scenario: Scenario,
    pool: AsyncConnectionPool,
    settings: Settings,
) -> Bundle:
    """Simulate, collect the reached set, join them. Records the result."""
    from fire_spread.router import get_deepfire

    started = time.perf_counter()
    perimeters = await get_deepfire().run_simulation_detailed(scenario.lat, scenario.lon)
    sim_s = time.perf_counter() - started
    log.info("scenario %s: simulated in %.1fs", scenario.scenario_id, sim_s)

    spread_payload = perimeters_to_payload(
        scenario.scenario_id, perimeters, scenario.declared_at
    )
    forecast = parse_spread(spread_payload)

    area = reached_area(forecast, settings.reached_margin_m)
    if area is None:
        # A valid forecast that never grew: the fuel at that point does not
        # carry fire. Nothing is reached, so nothing is at risk.
        log.warning("scenario %s: forecast has no contours", scenario.scenario_id)
        assets: list[Asset] = []
        assets_payload = {"type": "FeatureCollection", "features": []}
        facilities_error = None
    else:
        async with pool.connection() as conn:
            register = await register_assets_in_area(conn, settings, area)
        facilities, facilities_error = await asyncio.to_thread(
            facilities_in_area,
            area,
            OsmAssetProvider(endpoints=settings.overpass_urls or None),
        )
        assets = register + facilities
        assets_payload = _assets_to_payload(assets)

    exposures = compute_exposure(forecast, assets, scenario.as_engine_fire().ignition_point)
    _write(scenario, spread_payload, assets_payload, facilities_error)
    log.info(
        "scenario %s: bundle built in %.1fs (%d assets, %d named)",
        scenario.scenario_id,
        time.perf_counter() - started,
        len(assets),
        len([a for a in assets if a.source != "INSPIRE"]),
    )
    return Bundle(
        scenario=scenario,
        forecast=forecast,
        assets=assets,
        exposures=exposures,
        built_at=datetime.now(UTC),
        from_disk=False,
        facilities_error=facilities_error,
    )


def _assets_to_payload(assets: list[Asset]) -> dict:
    """Assets back to EPSG:4326 GeoJSON, for recording."""
    to_wgs = pyproj.Transformer.from_crs("EPSG:25831", "EPSG:4326", always_xy=True).transform
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": transform(to_wgs, a.geometry).__geo_interface__,
                "properties": {
                    "asset_id": a.asset_id,
                    "asset_type": a.asset_type,
                    "name": a.name,
                    "value": a.value,
                    "vulnerability": a.vulnerability,
                    "source": a.source,
                },
            }
            for a in assets
        ],
    }


# ------------------------------------------------------------------ access --


async def get_bundle(
    scenario: Scenario,
    pool: AsyncConnectionPool,
    settings: Settings,
) -> Bundle:
    """The scenario's bundle: memory, then disk, then a fresh simulation.

    The per-scenario lock is what stops two browser tabs queueing two
    simulations of the same ignition — Deepfire allows only two in flight for
    the whole client, so a duplicate is expensive twice over.
    """
    cached = _bundles.get(scenario.scenario_id)
    if cached is not None:
        return cached

    lock = _locks.setdefault(scenario.scenario_id, asyncio.Lock())
    async with lock:
        cached = _bundles.get(scenario.scenario_id)
        if cached is not None:
            return cached

        bundle = _read(scenario)
        if bundle is None:
            try:
                bundle = await _build(scenario, pool, settings)
            except Exception as exc:
                raise BundleUnavailable(
                    f"no recorded bundle for {scenario.scenario_id} and it could not "
                    f"be simulated: {exc}"
                ) from exc
        _bundles[scenario.scenario_id] = bundle
        return bundle


def clear_bundle(scenario_id: str) -> None:
    """Forget the in-memory bundle so the next request reloads or resimulates."""
    _bundles.pop(scenario_id, None)


def loaded_ids() -> list[str]:
    return sorted(_bundles)


def loaded_bundles() -> list[Bundle]:
    """The bundles currently in memory — what /api/health reports against."""
    return list(_bundles.values())


def has_recording(scenario_id: str) -> bool:
    return _path(scenario_id).exists()
