"""Fire arrival-grid endpoint, packaged as a router for mounting in a larger FastAPI app.

    from fire_spread import router
    app.include_router(router, prefix="/fire")

Reads DEEPFIRE_CLIENT_ID / DEEPFIRE_CLIENT_SECRET from .env (or the environment) on first request.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query

from .deepfire import DeepfireClient, DeepfireError
from .grid import GridTooLarge, build_arrival_grid

router = APIRouter(tags=["fire-spread"])


@lru_cache(maxsize=1)
def get_deepfire() -> DeepfireClient:
    load_dotenv()
    try:
        return DeepfireClient(os.environ["DEEPFIRE_CLIENT_ID"], os.environ["DEEPFIRE_CLIENT_SECRET"])
    except KeyError as e:
        raise HTTPException(status_code=500, detail=f"missing env var {e.args[0]}")


@router.get("/arrival-grid")
async def arrival_grid(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
) -> dict:
    """Simulate a point ignition and return the hour each grid cell is first reached."""
    try:
        hourly = await get_deepfire().run_simulation(lat, lon)
    except DeepfireError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    try:
        return build_arrival_grid(hourly, lat, lon)
    except GridTooLarge as e:
        raise HTTPException(status_code=500, detail=str(e))
