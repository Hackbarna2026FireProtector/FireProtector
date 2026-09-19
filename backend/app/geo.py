"""Geographic helpers: the two ways a caller can describe a box.

/building_specs takes a centre and a size in km; /assets takes a bbox string.
Both end up as a BoundingBox.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import cos, degrees, radians

# Mean Earth radius (IUGG). Good to ~0.3% for the box sizes we care about.
EARTH_RADIUS_KM = 6371.0088

# Below this cosine the east-west degree span explodes, so we just take the
# whole longitude range instead of dividing by (almost) zero.
_MIN_COS_LAT = 1e-9


@dataclass(frozen=True)
class BoundingBox:
    """A lat/lon box. `lon_ranges` holds two ranges when the box crosses ±180°."""

    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float
    lon_ranges: list[tuple[float, float]] = field(default_factory=list)


def square_bounding_box(latitude: float, longitude: float, size_km: float) -> BoundingBox:
    """Box of `size_km` x `size_km` centred on (latitude, longitude).

    The north-south side is exactly `size_km`; the east-west side is `size_km`
    measured along the parallel through the centre.
    """
    half_km = size_km / 2.0

    lat_delta = degrees(half_km / EARTH_RADIUS_KM)
    min_latitude = max(latitude - lat_delta, -90.0)
    max_latitude = min(latitude + lat_delta, 90.0)

    cos_lat = cos(radians(latitude))
    if cos_lat <= _MIN_COS_LAT:
        # At (or very near) a pole the box wraps all the way round.
        return BoundingBox(min_latitude, max_latitude, -180.0, 180.0, [(-180.0, 180.0)])

    lon_delta = degrees(half_km / (EARTH_RADIUS_KM * cos_lat))
    if lon_delta >= 180.0:
        return BoundingBox(min_latitude, max_latitude, -180.0, 180.0, [(-180.0, 180.0)])

    min_longitude = longitude - lon_delta
    max_longitude = longitude + lon_delta

    if min_longitude < -180.0:
        # Box straddles the antimeridian: split into two ranges.
        ranges = [(-180.0, max_longitude), (min_longitude + 360.0, 180.0)]
    elif max_longitude > 180.0:
        ranges = [(min_longitude, 180.0), (-180.0, max_longitude - 360.0)]
    else:
        ranges = [(min_longitude, max_longitude)]

    return BoundingBox(min_latitude, max_latitude, min_longitude, max_longitude, ranges)


# The contract's own pattern, character for character: four plain decimals
# separated by commas. It admits no spaces, no exponent form and no leading
# plus, so neither do we -- a caller sending "1e2" or " 1.0, 41.6" has a bug
# worth surfacing rather than guessing at.
_BBOX = re.compile(r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$")

_BBOX_FORM = "minLon,minLat,maxLon,maxLat in EPSG:4326 degrees, e.g. 1.0,41.6,1.6,42.0"


class BboxError(ValueError):
    """The bbox parameter cannot be read as a box."""


def parse_bbox(raw: str | None) -> BoundingBox:
    """Turn the contract's bbox string into a BoundingBox.

    Note the order: longitude first, which is the opposite of the lat/lon
    parameters /building_specs takes.
    """
    if raw is None or raw == "":
        raise BboxError(f"'bbox' is required: {_BBOX_FORM}.")
    if not _BBOX.match(raw):
        raise BboxError(f"'bbox' is malformed: expected {_BBOX_FORM}, got {raw!r}.")

    min_longitude, min_latitude, max_longitude, max_latitude = (float(v) for v in raw.split(","))

    for name, value, limit in (
        ("latitude", min_latitude, 90.0),
        ("latitude", max_latitude, 90.0),
        ("longitude", min_longitude, 180.0),
        ("longitude", max_longitude, 180.0),
    ):
        if not -limit <= value <= limit:
            raise BboxError(f"'bbox' {name} {value} is outside -{limit:g}..{limit:g}.")

    if min_latitude > max_latitude:
        raise BboxError(f"'bbox' minLat {min_latitude} is above maxLat {max_latitude}.")
    if min_longitude > max_longitude:
        raise BboxError(f"'bbox' minLon {min_longitude} is above maxLon {max_longitude}.")

    return BoundingBox(
        min_latitude=min_latitude,
        max_latitude=max_latitude,
        min_longitude=min_longitude,
        max_longitude=max_longitude,
        lon_ranges=[(min_longitude, max_longitude)],
    )
