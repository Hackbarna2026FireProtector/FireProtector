"""The reached set: which assets a forecast actually threatens.

Two populations, joined into one list because the scoring model treats them
identically:

* **register assets** — INSPIRE building points from Postgres. Millions of
  them, and every one is named ``"residential"``. They are what lets the
  summary say *1,847 homes and 12 storage tanks are inside the two-hour
  envelope*; they can never say which ones.
* **critical facilities** — named, typed places from OpenStreetMap. Far fewer,
  and the only reason the ranked list can show a hospital by name.

Only assets the fire reaches are collected. That is not an optimisation: an
asset outside the outermost contour has no arrival time, so ``f_urgency`` is 0
and its risk is exactly 0. Scoring the surrounding region would add six figures
of guaranteed-zero rows to every response and to all thirteen sensitivity
passes.

The query runs in two stages — a bbox filter in SQL, which the
``(latitude, longitude)`` index serves, then exact containment in shapely —
because the database holds no geometry to intersect against.
"""

from __future__ import annotations

import logging

import pyproj
from psycopg import AsyncConnection, sql
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.prepared import prep

from app.config import Settings
from app.engine.contracts import Asset, SpreadForecast, sanitize_name
from app.geo import BoundingBox
from app.providers.osm_assets import OsmAssetProvider
from app.queries import _bbox_predicate, _table_identifier

log = logging.getLogger(__name__)

# The engine works in EPSG:25831 metres; Postgres and OSM speak degrees.
_TO_WGS84 = pyproj.Transformer.from_crs("EPSG:25831", "EPSG:4326", always_xy=True).transform


def reached_area(forecast: SpreadForecast, margin_m: float) -> BaseGeometry | None:
    """The forecast's footprint plus a margin, in EPSG:25831. None if empty."""
    if not forecast.contours:
        return None
    return unary_union([c.geometry for c in forecast.contours]).buffer(margin_m)


def area_to_bbox(area: BaseGeometry) -> BoundingBox:
    """Lat/lon envelope of a metric geometry, for the SQL prefilter."""
    min_lon, min_lat, max_lon, max_lat = transform(_TO_WGS84, area).bounds
    return BoundingBox(
        min_latitude=min_lat,
        max_latitude=max_lat,
        min_longitude=min_lon,
        max_longitude=max_lon,
    )


async def register_assets_in_area(
    conn: AsyncConnection,
    settings: Settings,
    area: BaseGeometry,
) -> list[Asset]:
    """Register rows whose point falls inside ``area`` (EPSG:25831).

    Unpaged on purpose. ``GET /assets`` pages because it is a public endpoint
    with an unbounded box; this query is bounded by a burn perimeter, and a
    caller that stopped at the first page would rank a thousand arbitrary
    buildings and present them as the whole picture.
    """
    bbox = area_to_bbox(area)
    where, params = _bbox_predicate(settings, bbox)
    query = sql.SQL(
        "SELECT 'asset-' || asset_id AS wire_id, asset_type, name, value, "
        "       vulnerability, source, {lat} AS lat, {lon} AS lon "
        "FROM {assets} WHERE {where}"
    ).format(
        assets=_table_identifier(settings.asset_specs_table),
        where=where,
        lat=sql.Identifier(settings.latitude_column),
        lon=sql.Identifier(settings.longitude_column),
    )

    async with conn.cursor() as cur:
        await cur.execute(query, params)
        rows = await cur.fetchall()

    to_metric = pyproj.Transformer.from_crs(
        "EPSG:4326", "EPSG:25831", always_xy=True
    ).transform
    contains = prep(area).contains

    assets: list[Asset] = []
    for row in rows:
        point = transform(to_metric, Point(float(row["lon"]), float(row["lat"])))
        if not contains(point):
            continue
        assets.append(
            Asset(
                asset_id=row["wire_id"],
                asset_type=row["asset_type"],
                name=sanitize_name(row["name"] or ""),
                # Clamped exactly as GET /assets clamps them, so the two views
                # of a row never disagree.
                value=min(100.0, max(1.0, float(row["value"]))),
                vulnerability=min(1.0, max(0.0, float(row["vulnerability"]))),
                source=row["source"],
                geometry=point,
            )
        )
    log.info("register assets: %d in bbox, %d inside the burn", len(rows), len(assets))
    return assets


def facilities_in_area(
    area: BaseGeometry, provider: OsmAssetProvider
) -> tuple[list[Asset], str | None]:
    """Named critical facilities inside ``area``, and why there are none.

    Returns ``(facilities, error)``. A failure degrades the ranked list to
    unnamed register rows rather than failing the request — the summary and the
    map are still correct without it — but it is reported rather than
    swallowed. An empty list with ``error=None`` means Overpass answered and
    there genuinely is no hospital in the burn; an empty list with an error
    means the named layer is missing, and the two must never look alike.
    """
    bbox = area_to_bbox(area)
    try:
        candidates = provider.fetch_assets(
            (bbox.min_longitude, bbox.min_latitude, bbox.max_longitude, bbox.max_latitude)
        )
    except Exception as exc:  # noqa: BLE001 - degraded, not fatal
        log.warning("OSM facilities unavailable: %s", exc)
        return [], f"{exc.__class__.__name__}: {exc}"

    contains = prep(area).intersects
    return [a for a in candidates if contains(a.geometry)], None
