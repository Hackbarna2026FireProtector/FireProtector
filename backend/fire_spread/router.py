"""HTTP surface: one synchronous prediction endpoint plus health/data-info.

    from fire_spread.router import router
    app.include_router(router, prefix="/fire")
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import ORJSONResponse

from .elmfire_runner import elmfire_available
from .models import ArrivalGrid, Ignition, PipelineError, SimulationRequest
from .pipeline import Pipeline
from .settings import get_settings

router = APIRouter(tags=["fire-spread"])


@lru_cache(maxsize=1)
def get_pipeline() -> Pipeline:
    return Pipeline()


@lru_cache(maxsize=1)
def get_semaphore() -> asyncio.Semaphore:
    return asyncio.Semaphore(get_settings().max_concurrent_runs)


@router.get("/health")
async def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "elmfire": elmfire_available(),
        "dataDir": str(s.data_dir),
        "dataPresent": (s.data_dir / "dem.tif").exists(),
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


@router.get("/arrival-grid", response_model=ArrivalGrid, response_model_exclude_none=True, response_class=ORJSONResponse)
async def arrival_grid(
    lat: float = Query(ge=-90, le=90, description="Ignition latitude (WGS84)"),
    lon: float = Query(ge=-180, le=180, description="Ignition longitude (WGS84)"),
    durationHours: int = Query(24, ge=1, le=48),
    ensembleMembers: int = Query(16, ge=1, le=64),
    startTime: datetime | None = Query(None, description="ISO 8601 ignition time (default: now)"),
    seed: int | None = Query(None, ge=1),
    spotting: bool | None = Query(None, description="Ember transport (slower); default from settings"),
    debug: bool = Query(False),
) -> ORJSONResponse:
    """Run an ELMFIRE ensemble from a point ignition and return the arrival grid."""
    s = get_settings()
    if not (s.data_dir / "dem.tif").exists():
        raise HTTPException(status_code=503, detail="static data not prepared (run scripts/setup_fire_data.sh)")
    sem = get_semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=s.acquire_timeout_s)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="simulation slots busy; retry later")
    try:
        req = SimulationRequest(
            ignition=Ignition(lat=lat, lon=lon),
            duration_hours=durationHours,
            ensemble_members=ensembleMembers,
            start_time=startTime,
            seed=seed,
            spotting=spotting,
            debug=debug,
        )
        grid = await get_pipeline().run(req)
        # Bypass FastAPI's re-validation + jsonable_encoder walk: the grids hold millions of
        # scalars and orjson serialises them ~20x faster.
        return ORJSONResponse(grid.model_dump(exclude_none=True))
    except PipelineError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    finally:
        sem.release()
