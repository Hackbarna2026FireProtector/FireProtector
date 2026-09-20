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


CREDENTIAL_VARS = ("DEEPFIRE_CLIENT_ID", "DEEPFIRE_CLIENT_SECRET")


def missing_credentials() -> list[str]:
    """Which Deepfire variables are unset, loading .env first.

    Anything asking "can this deployment simulate?" goes through here rather
    than reading os.environ directly. The credentials live in backend/.env and
    only reach the environment once load_dotenv has run, so a bare os.environ
    check reports them missing on a host where they are configured perfectly
    well -- which is how /api/health came to claim a working deployment could
    not forecast anything.
    """
    load_dotenv()
    # Blank counts as missing: docker compose passes the variables through as
    # empty strings when the host has not set them, and an empty secret would
    # otherwise surface as an opaque 502 from Deepfire's token endpoint.
    return [name for name in CREDENTIAL_VARS if not (os.environ.get(name) or "").strip()]


@lru_cache(maxsize=1)
def get_deepfire() -> DeepfireClient:
    missing = missing_credentials()
    if missing:
        # Not cached: lru_cache only stores return values, so setting the
        # variables and restarting the worker is enough to recover.
        raise HTTPException(status_code=500, detail=f"missing env var {', '.join(missing)}")
    return DeepfireClient(*((os.environ[name] or "").strip() for name in CREDENTIAL_VARS))


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
