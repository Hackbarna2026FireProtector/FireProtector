"""GET /building_specs — buildings inside a square centred on a coordinate."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from psycopg_pool import AsyncConnectionPool

from ..config import Settings, get_settings
from ..db import get_pool
from ..errors import translate_db_errors
from ..geo import square_bounding_box
from ..queries import fetch_buildings_in_box
from ..schemas import Bounds, BuildingSpecsResponse, Center

router = APIRouter(tags=["buildings"])


@router.get("/building_specs", response_model=BuildingSpecsResponse)
async def get_building_specs(
    lat: float = Query(
        ..., ge=-90, le=90, description="Latitude of the square's centre (WGS84 degrees)."
    ),
    lon: float = Query(
        ..., ge=-180, le=180, description="Longitude of the square's centre (WGS84 degrees)."
    ),
    size_km: float = Query(
        ...,
        gt=0,
        le=1000,
        description="Side length of the square in kilometres; the centre sits in the middle.",
    ),
    limit: int | None = Query(None, gt=0, description="Maximum number of rows to return."),
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> BuildingSpecsResponse:
    effective_limit = min(limit or settings.default_limit, settings.max_limit)
    bbox = square_bounding_box(lat, lon, size_km)

    async with pool.connection() as conn:
        with translate_db_errors(settings):
            rows = await fetch_buildings_in_box(
                conn, settings, bbox, lat, lon, effective_limit
            )

    return BuildingSpecsResponse(
        center=Center(latitude=lat, longitude=lon),
        size_km=size_km,
        bounds=Bounds(
            min_latitude=bbox.min_latitude,
            max_latitude=bbox.max_latitude,
            min_longitude=bbox.min_longitude,
            max_longitude=bbox.max_longitude,
        ),
        count=len(rows),
        limit=effective_limit,
        truncated=len(rows) == effective_limit,
        buildings=rows,
    )
