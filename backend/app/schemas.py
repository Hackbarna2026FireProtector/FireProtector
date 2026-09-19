"""Response models for the API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Center(BaseModel):
    latitude: float
    longitude: float


class Bounds(BaseModel):
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float


class BuildingSpecsResponse(BaseModel):
    center: Center
    size_km: float = Field(description="Side length of the query square, in kilometres.")
    bounds: Bounds
    count: int = Field(description="Number of rows returned.")
    limit: int
    truncated: bool = Field(
        description="True when the row cap was hit and more buildings may exist in the box."
    )
    buildings: list[dict[str, Any]] = Field(
        description="Matching rows, all columns as stored, nearest to the centre first."
    )


class HealthResponse(BaseModel):
    status: str
    database: str
    detail: str | None = None


class AddBuildingResponse(BaseModel):
    inserted: int = Field(description="Number of rows written.")
    buildings: list[dict[str, Any]] = Field(
        description="The rows as stored, including database-generated columns such as the id."
    )
