"""Geographic helpers: turn a centre point plus a size in km into a lat/lon box."""

from __future__ import annotations

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
