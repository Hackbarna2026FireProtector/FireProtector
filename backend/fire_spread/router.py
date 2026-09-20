"""HTTP surface: the synchronous prediction endpoint (GET for a point, POST for a fire
state with an optional perimeter) plus health/data-info.

    from fire_spread.router import router, startup
    app.include_router(router, prefix="/fire")   # and call startup() in the lifespan

Normal-running mode: the API serves predictions on live Open-Meteo weather with the
pipeline mode from ``PIPELINE_MODE`` (``base`` or ``tuned``, see ``modes.py``); a request
may pick the other mode with ``mode=``. The evaluation loop
(``scripts/fire_spread/evaluate.py``) replays both modes on historical weather.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse

from .elmfire_runner import elmfire_available
from .models import ArrivalGrid, FireStateRequest, Ignition, PipelineError, PipelineMode, SimulationRequest
from .pipeline import Pipeline
from .settings import get_settings

log = logging.getLogger("fire_spread")
router = APIRouter(tags=["fire-spread"])


@lru_cache(maxsize=4)
def get_pipeline(mode: str | None = None) -> Pipeline:
    """One pipeline per mode (lazily built; ``mode=None`` = the configured one)."""
    return Pipeline(mode=mode or get_settings().pipeline_mode)


@lru_cache(maxsize=1)
def get_semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(get_settings().max_concurrent_runs)


def data_present() -> bool:
    return (get_settings().data_dir / "dem.tif").exists()


def status() -> str:
    """``ready`` | ``no elmfire`` | ``no data`` - what ``/health`` reports."""
    if not elmfire_available():
        return "no elmfire"
    if not data_present():
        return "no data"
    return "ready"


def startup() -> str:
    """Called from the app lifespan: log the configured mode and readiness and warm the
    pipeline for it (opens the static tier once) so the first request pays nothing extra.
    Never raises - a missing tier or binary is a health status, not a startup failure."""
    s = get_settings()
    st = status()
    log.info("fire_spread: mode=%s status=%s data_dir=%s runs_dir=%s", s.pipeline_mode, st, s.data_dir, s.runs_dir)
    if st == "ready":
        try:
            get_pipeline(s.pipeline_mode).landscape  # noqa: B018 - property opens dem.tif
        except Exception as e:  # pragma: no cover - surfaced at request time as a 500 anyway
            log.warning("fire_spread: could not open the static tier: %s", e)
    return st


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "elmfire": elmfire_available(),
        "dataDir": str(s.data_dir),
        "dataPresent": data_present(),
        "mode": s.pipeline_mode,
    }


@router.get("/data-info")
async def data_info() -> dict:
    """Manifest of the static tier (grid, sources, dates, licenses)."""
    s = get_settings()
    p = s.data_dir / "manifest.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="static data not prepared (run scripts/setup_fire_data.sh)")
    import json

    return json.loads(p.read_text())


async def _simulate(req: SimulationRequest) -> ORJSONResponse:
    s = get_settings()
    if not data_present():
        raise HTTPException(status_code=503, detail="static data not prepared (run scripts/setup_fire_data.sh)")
    sem = get_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=s.acquire_timeout_s)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="simulation slots busy; retry later")
    try:
        grid = await get_pipeline(req.mode or s.pipeline_mode).run(req)
        # Bypass FastAPI's re-validation + jsonable_encoder walk: the grids hold millions of
        # scalars and orjson serialises them ~20x faster.
        return ORJSONResponse(grid.model_dump(exclude_none=True))
    except PipelineError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    finally:
        sem.release()


@router.get("/arrival-grid", response_model=ArrivalGrid, response_model_exclude_none=True, response_class=ORJSONResponse)
async def arrival_grid(
    lat: float = Query(ge=-90, le=90, description="Ignition latitude (WGS84)"),
    lon: float = Query(ge=-180, le=180, description="Ignition longitude (WGS84)"),
    durationHours: int = Query(24, ge=1, le=48),
    ensembleMembers: int = Query(16, ge=1, le=64),
    startTime: datetime | None = Query(None, description="ISO 8601 ignition time (default: now)"),
    seed: int | None = Query(None, ge=1),
    spotting: bool | None = Query(None, description="Ember transport (slower); default from settings"),
    mode: PipelineMode | None = Query(None, description="Pipeline mode: base | tuned (default: PIPELINE_MODE)"),
    debug: bool = Query(False),
) -> ORJSONResponse:
    """Run an ELMFIRE ensemble from a point ignition and return the arrival grid."""
    return await _simulate(SimulationRequest(
        ignition=Ignition(lat=lat, lon=lon),
        duration_hours=durationHours, ensemble_members=ensembleMembers, start_time=startTime,
        seed=seed, spotting=spotting, mode=mode, debug=debug,
    ))


@router.post("/arrival-grid", response_model=ArrivalGrid, response_model_exclude_none=True, response_class=ORJSONResponse)
async def arrival_grid_from_state(body: FireStateRequest) -> ORJSONResponse:
    """Run an ELMFIRE ensemble from an initial fire state - a point and/or an active
    perimeter (GeoJSON polygon, lit along its boundary at t 0) - and return the arrival grid.
    With only a perimeter the reference point is its centroid."""
    if body.perimeter is not None:
        if body.ignition is not None:
            lat, lon = body.ignition.lat, body.ignition.lon
        else:
            from shapely.geometry import shape

            try:
                c = shape(body.perimeter).centroid
                lat, lon = float(c.y), float(c.x)
            except Exception as e:  # malformed coordinates
                raise HTTPException(status_code=422, detail=f"invalid perimeter geometry: {e}")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise HTTPException(status_code=422, detail="perimeter coordinates must be WGS84 lon/lat")
        ign = Ignition(lat=lat, lon=lon, perimeter=body.perimeter)
    else:
        ign = Ignition(lat=body.ignition.lat, lon=body.ignition.lon)
    return await _simulate(SimulationRequest(
        ignition=ign,
        duration_hours=body.durationHours, ensemble_members=body.ensembleMembers, start_time=body.startTime,
        seed=body.seed, spotting=body.spotting, mode=body.mode, debug=body.debug,
    ))
