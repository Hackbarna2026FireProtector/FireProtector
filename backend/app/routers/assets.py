"""GET /assets — assets inside a bounding box, as a GeoJSON FeatureCollection.

Implements the asset-register contract. Two things about it are worth knowing:

* `bbox` is longitude-first, the opposite order of the lat/lon parameters
  /building_specs takes.
* The contract has no paging, so a bare request returns the first page plus a
  `next` link. A consumer that ignores `next` reads one page and believes it
  has the whole box.

Every parameter is taken as a string and checked here, so FastAPI's own
validation never fires for this route: the contract answers a bad bbox with
400, and FastAPI's default would be 422.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg_pool import AsyncConnectionPool

from ..config import Settings, get_settings
from ..db import get_pool
from ..errors import translate_db_errors
from ..geo import BboxError, parse_bbox
from ..queries import count_assets_in_bbox, fetch_assets_in_bbox
from ..schemas import AssetCollection, AssetFeature, AssetProperties
from ..vulnerability import vulnerability

router = APIRouter(tags=["assets"])

# The contract caps a name at 120 characters and treats it as untrusted text.
# We are the ones producing it, so we do the capping rather than relying on the
# consumer to cope.
_MAX_NAME = 120


def _clean_name(value: str | None) -> str:
    """Printable, trimmed, and within the contract's length limit."""
    text = "".join(ch for ch in (value or "") if ch.isprintable()).strip()
    if len(text) > _MAX_NAME:
        text = text[: _MAX_NAME - 1].rstrip() + "…"
    return text or "unnamed"


def _positive_int(raw: str | None, name: str, default: int, minimum: int) -> int:
    """Read an integer query parameter, or raise the contract's 400."""
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise HTTPException(400, f"'{name}' must be a whole number, got {raw!r}.") from None
    if value < minimum:
        raise HTTPException(400, f"'{name}' must be {minimum} or more, got {value}.")
    return value


def _feature(row: dict[str, Any]) -> AssetFeature:
    # Clamped, so a replacement vulnerability model cannot produce a response
    # the consumer rejects.
    score = min(max(float(vulnerability(row)), 0.0), 1.0)
    # The column is 1-100 by contract; a row scored outside it is pulled back
    # rather than failing the whole page.
    value = min(max(float(row["value"]), 1.0), 100.0)

    return AssetFeature(
        geometry=row["geometry"],
        properties=AssetProperties(
            asset_id=row["wire_id"],
            asset_type=row["asset_type"],
            name=_clean_name(row["name"]),
            value=value,
            vulnerability=score,
            source=row["source"],
        ),
    )


@router.get(
    "/assets",
    response_model=AssetCollection,
    response_model_exclude_none=False,
    summary="Assets inside a bounding box",
)
async def get_assets(
    request: Request,
    bbox: str | None = Query(
        None,
        description="minLon,minLat,maxLon,maxLat in EPSG:4326 degrees.",
        examples=["1.0,41.6,1.6,42.0"],
    ),
    limit: str | None = Query(None, description="Features per page. Defaults to the page size."),
    offset: str | None = Query(None, description="Features to skip. Defaults to 0."),
    pool: AsyncConnectionPool = Depends(get_pool),
    settings: Settings = Depends(get_settings),
) -> AssetCollection:
    try:
        box = parse_bbox(bbox)
    except BboxError as exc:
        raise HTTPException(400, str(exc)) from exc

    page_size = settings.assets_page_size
    # Asking for more than a page's worth yields a page's worth: the ceiling and
    # the default are the same number.
    requested = _positive_int(limit, "limit", page_size, minimum=1)
    effective_limit = min(requested, page_size)
    effective_offset = _positive_int(offset, "offset", 0, minimum=0)

    async with pool.connection() as conn:
        with translate_db_errors(settings):
            total = await count_assets_in_bbox(conn, settings, box)
            rows = await fetch_assets_in_bbox(
                conn, settings, box, effective_limit, effective_offset
            )

    next_offset = effective_offset + len(rows)
    next_url = (
        str(request.url.include_query_params(offset=next_offset, limit=effective_limit))
        if next_offset < total
        else None
    )

    return AssetCollection(
        features=[_feature(row) for row in rows],
        numberMatched=total,
        numberReturned=len(rows),
        next=next_url,
    )
