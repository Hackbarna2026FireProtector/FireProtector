"""Response models for the API."""

from __future__ import annotations

from typing import Any, Literal

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
    fire_spread: Literal["ready", "no elmfire", "no data"] = Field(
        description="Whether /fire/arrival-grid can run: the ELMFIRE binary and the static tier are both present."
    )
    detail: str | None = None


class AddBuildingResponse(BaseModel):
    inserted: int = Field(description="Number of rows written.")
    buildings: list[dict[str, Any]] = Field(
        description="The rows as stored, including database-generated columns such as the id."
    )


# --------------------------------------------------------------- /assets ----
# Field names follow the contract rather than Python convention: numberMatched
# and numberReturned go on the wire exactly as written here.


class AssetProperties(BaseModel):
    """The six properties the contract requires on every feature."""

    asset_id: str = Field(description='Unique within a response, e.g. "asset-12345".')
    asset_type: str = Field(
        description="Open list: mostly 'residential', plus the INSPIRE building "
        "natures and 'forest'."
    )
    name: str = Field(max_length=120)
    value: float = Field(ge=1, le=100, description="Relative importance.")
    vulnerability: float = Field(ge=0, le=1, description="Susceptibility to fire damage.")
    source: str = Field(description="Provenance of the record.")


class AssetFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any] = Field(description="GeoJSON Point, Polygon or MultiPolygon.")
    properties: AssetProperties


class AssetCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[AssetFeature]
    numberMatched: int = Field(  # noqa: N815 - contract spelling
        description="Total features in the bbox, across every page."
    )
    numberReturned: int = Field(  # noqa: N815 - contract spelling
        description="Features on this page."
    )
    next: str | None = Field(
        default=None,
        description="URL of the following page, or null on the last one. A caller "
        "that ignores this reads only the first page.",
    )


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    """The contract's error envelope, used for every error the API returns."""

    error: ErrorBody
