"""POST /add_building — insert building rows into the table /building_specs reads."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from psycopg_pool import AsyncConnectionPool

from ..config import Settings, get_settings
from ..db import get_pool
from ..errors import missing_table, translate_db_errors
from ..payload import PayloadError, insert_column_order, normalize_rows
from ..queries import fetch_table_columns, insert_buildings
from ..schemas import AddBuildingResponse

router = APIRouter(tags=["buildings"])

_EXAMPLES = {
    "single": {
        "summary": "One building",
        "value": {
            "name": "Hospital Comarcal",
            "latitude": 41.84,
            "longitude": 1.30,
        },
    },
    "bulk": {
        "summary": "Several buildings at once",
        "value": [
            {"name": "Escola Segarra", "latitude": 41.82, "longitude": 1.27},
            {"name": "Substation East", "latitude": 41.78, "longitude": 1.31},
        ],
    },
}


@router.post("/add_building", response_model=AddBuildingResponse, status_code=201)
async def add_building(
    payload: dict[str, Any] | list[dict[str, Any]] = Body(
        ...,
        openapi_examples=_EXAMPLES,
        description=(
            "A building object, or a list of them. Keys must be columns of the "
            "building table; latitude and longitude are required, anything else "
            "is optional and falls back to the column's default."
        ),
    ),
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> AddBuildingResponse:
    async with pool.connection() as conn:
        with translate_db_errors(settings):
            # Validate against the table as it actually is, so a typo comes back
            # as a clear 400 rather than a raw Postgres error.
            columns = await fetch_table_columns(conn, settings)
            if not columns:
                raise missing_table(settings)

            try:
                rows = normalize_rows(
                    payload,
                    latitude_column=settings.latitude_column,
                    longitude_column=settings.longitude_column,
                    columns=columns,
                    max_rows=settings.max_insert_rows,
                )
            except PayloadError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc

            stored = await insert_buildings(
                conn, settings, rows, insert_column_order(rows, columns)
            )

    return AddBuildingResponse(inserted=len(stored), buildings=stored)
