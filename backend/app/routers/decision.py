"""The decision layer, mounted under /api.

This is the UI's API. It is kept separate from the root routes on purpose: the
root serves the asset-register contract that other people's code is written
against and is not ours to reshape, while everything here exists to answer one
question for one front end — given this ignition, what should be protected
first, and how much should that ordering be trusted.

Scoring, sensitivity and briefing are synchronous CPU work over a cached
bundle. They are declared ``def`` rather than ``async def`` so FastAPI runs
them in its threadpool: sensitivity re-scores the whole reached set thirteen
times, and on the event loop that would stall every other request, including
the map's own.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Body, Depends, HTTPException
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..db import get_pool
from ..decision import serializers
from ..decision.bundle import (
    Bundle,
    BundleUnavailable,
    clear_bundle,
    get_bundle,
    has_recording,
    loaded_bundles,
)
from ..decision.scenarios import ScenarioNotFound, get_scenario, list_scenarios
from ..decision_config import Config
from ..engine.scoring import ScoreParams, score_assets
from ..engine.sensitivity import sensitivity

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["decision"])

# Mirrored by GET /api/config/defaults, which is what draws the UI's sliders.
PARAM_RANGES: dict[str, tuple[float, float]] = {
    "tau": (15.0, 360.0),
    "w_value": (0.0, 3.0),
    "w_conf": (0.0, 3.0),
    "w_vuln": (0.0, 3.0),
    "w_urgency": (0.0, 3.0),
    "horizon": (0.0, 1440.0),
}
PARAM_NOTES: dict[str, str] = {
    "tau": "Urgency half-life in minutes: how fast risk decays with arrival time.",
    "w_conf": "Weight on ensemble agreement — how much of the Deepfire ensemble burned the asset.",
    "horizon": "Scoring cap in minutes. Assets arriving later score zero; contours still draw.",
}


class BriefingRequest(BaseModel):
    parameters: ScoreParams = Field(default_factory=ScoreParams)
    top_n: int = Field(default=5, ge=1, le=20)


async def _bundle(
    scenario_id: str,
    pool: AsyncConnectionPool,
    settings: Settings,
) -> Bundle:
    """Resolve a scenario and its bundle, or raise the right HTTP error."""
    try:
        scenario = get_scenario(scenario_id)
    except ScenarioNotFound:
        raise HTTPException(404, f"No ignition scenario {scenario_id!r}.") from None
    try:
        return await get_bundle(scenario, pool, settings)
    except BundleUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


# ------------------------------------------------------------------ meta ----


@router.get("/health", summary="Decision layer health and data provenance")
async def health(
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> dict:
    """What the header badge reads.

    ``data_mode`` is about provenance, not correctness: *live* means a fresh
    simulation is possible, *cached* means answers come from recorded bundles,
    and *degraded* means neither — nothing can be forecast at all.
    """
    from fire_spread.router import missing_credentials

    providers: dict[str, dict] = {}

    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute("SELECT 1")
            await cur.fetchone()
        providers["postgres"] = {"source": "asset register", "available": True, "error": None}
    except Exception as exc:  # noqa: BLE001 - a status, not a 500
        providers["postgres"] = {
            "source": "asset register",
            "available": False,
            "error": f"{exc.__class__.__name__}: {exc}",
        }

    missing = missing_credentials()
    providers["deepfire"] = {
        "source": "fire spread",
        "available": not missing,
        "error": None if not missing else f"not set: {', '.join(missing)}",
    }
    # Reported from the bundles actually built, not from a probe: a mirror can
    # answer normally and still hold the wrong extract, so the only honest
    # signal is whether the named layer arrived for a real query. Before any
    # scenario is loaded there is no evidence either way, and saying so beats
    # reporting a health we have not observed.
    bundles = loaded_bundles()
    osm_errors = [b.facilities_error for b in bundles if b.facilities_error]
    providers["overpass"] = {
        "source": "named facilities",
        "available": not osm_errors,
        "error": (
            osm_errors[0]
            if osm_errors
            else (None if bundles else "not queried yet — no scenario loaded")
        ),
    }
    nebius = bool(settings.nebius_api_key)
    providers["nebius"] = {
        "source": "briefings",
        "available": nebius,
        "error": None if nebius else "no API key; using deterministic templates",
    }

    recorded = [s.scenario_id for s in list_scenarios() if has_recording(s.scenario_id)]
    if not missing:
        data_mode = "live"
    elif recorded:
        data_mode = "cached"
    else:
        data_mode = "degraded"

    return {
        "status": "ok" if providers["postgres"]["available"] else "degraded",
        "data_mode": data_mode,
        "providers": providers,
        "recorded_scenarios": recorded,
    }


@router.get("/config/defaults", summary="Scoring parameter defaults and bounds")
def config_defaults() -> dict:
    defaults = ScoreParams()
    parameters = {}
    for name, (lo, hi) in PARAM_RANGES.items():
        parameters[name] = {
            "default": getattr(defaults, name, None),
            "min": lo,
            "max": hi,
        }
        if name in PARAM_NOTES:
            parameters[name]["note"] = PARAM_NOTES[name]
    return {"parameters": parameters}


# ------------------------------------------------------------- scenarios ----


@router.get("/scenarios", summary="The ignition scenarios this deployment knows")
def scenarios() -> dict:
    """Hypothetical ignitions, not detected fires — see CONTEXT.md."""
    return {"scenarios": [s.to_dict() for s in list_scenarios()]}


@router.get("/scenarios/{scenario_id}/spread", summary="Arrival-time contours")
async def spread(
    scenario_id: str,
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> dict:
    bundle = await _bundle(scenario_id, pool, settings)
    return serializers.forecast_to_geojson(bundle.forecast)


@router.get("/scenarios/{scenario_id}/assets", summary="The reached set, unscored")
async def assets(
    scenario_id: str,
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> dict:
    bundle = await _bundle(scenario_id, pool, settings)
    return serializers.assets_to_geojson(bundle.assets)


@router.post("/scenarios/{scenario_id}/refresh", summary="Drop the cached bundle")
def refresh(scenario_id: str) -> dict:
    """Forget the in-memory bundle. The recording on disk is kept: delete the
    file under data/bundles/ to force a fresh simulation."""
    clear_bundle(scenario_id)
    return {"refreshed": True, "scenario_id": scenario_id}


# --------------------------------------------------------------- analysis ---


@router.post("/scenarios/{scenario_id}/score", summary="Rank the reached set")
async def score(
    scenario_id: str,
    params: ScoreParams = Body(default_factory=ScoreParams),
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> dict:
    bundle = await _bundle(scenario_id, pool, settings)
    started = time.perf_counter()
    result = await _score_in_threadpool(bundle, params)
    log.info(
        "score %s: %d assets in %.0f ms",
        scenario_id,
        len(bundle.assets),
        (time.perf_counter() - started) * 1000,
    )
    payload = serializers.scored_result_to_payload(result, bundle.assets)
    # Whether the ranking has any names in it at all. Register rows are all
    # called "residential", so with the named layer missing the list is a
    # ranking of anonymous buildings — true, but not what it looks like.
    payload["named_layer"] = {
        "available": bundle.facilities_error is None,
        "count": len(bundle.named_assets),
        "error": bundle.facilities_error,
    }
    return payload


@router.post("/scenarios/{scenario_id}/sensitivity", summary="How stable is that ranking")
async def sensitivity_route(
    scenario_id: str,
    params: ScoreParams = Body(default_factory=ScoreParams),
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> dict:
    bundle = await _bundle(scenario_id, pool, settings)
    started = time.perf_counter()
    result = await _sensitivity_in_threadpool(bundle, params)
    log.info(
        "sensitivity %s: %d assets x 13 passes in %.0f ms",
        scenario_id,
        len(bundle.assets),
        (time.perf_counter() - started) * 1000,
    )
    return serializers.sensitivity_to_payload(result)


@router.post("/scenarios/{scenario_id}/briefing", summary="Trilingual incident briefing")
async def briefing(
    scenario_id: str,
    request: BriefingRequest = Body(default_factory=BriefingRequest),
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> dict:
    bundle = await _bundle(scenario_id, pool, settings)
    return await _briefing_in_threadpool(bundle, request, settings)


# The three blocking calls, isolated so the route bodies stay readable.
# starlette's run_in_threadpool is what `def` endpoints use internally; calling
# it explicitly keeps these endpoints `async` so the bundle await above stays
# on the event loop where it belongs.


async def _score_in_threadpool(bundle: Bundle, params: ScoreParams):
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(score_assets, bundle.assets, bundle.exposures, params)


async def _sensitivity_in_threadpool(bundle: Bundle, params: ScoreParams):
    from starlette.concurrency import run_in_threadpool

    return await run_in_threadpool(sensitivity, bundle.assets, bundle.exposures, params)


async def _briefing_in_threadpool(
    bundle: Bundle, request: BriefingRequest, settings: Settings
) -> dict:
    from starlette.concurrency import run_in_threadpool

    from ..briefing.facts import build_facts
    from ..briefing.service import generate_briefing

    def work() -> dict:
        result = score_assets(bundle.assets, bundle.exposures, request.parameters)
        robustness = sensitivity(
            bundle.assets, bundle.exposures, request.parameters
        ).robustness
        facts = build_facts(
            bundle.scenario.as_engine_fire(),
            bundle.forecast,
            result,
            robustness,
            top_n=request.top_n,
        )
        return generate_briefing(facts, Config.from_settings(settings))

    return await run_in_threadpool(work)
