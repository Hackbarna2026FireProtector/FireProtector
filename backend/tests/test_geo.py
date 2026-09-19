"""The box maths is the one thing that can be silently wrong, so pin it down."""

from math import cos, radians

import pytest

from app.geo import EARTH_RADIUS_KM, BboxError, parse_bbox, square_bounding_box


def _km_per_degree_lat() -> float:
    return EARTH_RADIUS_KM * radians(1.0)


def _km_per_degree_lon(latitude: float) -> float:
    return EARTH_RADIUS_KM * radians(1.0) * cos(radians(latitude))


@pytest.mark.parametrize("size_km", [0.5, 5.0, 10.0, 100.0])
def test_sides_measure_the_requested_length(size_km: float) -> None:
    lat, lon = 41.80, 1.25  # La Segarra, Catalonia
    box = square_bounding_box(lat, lon, size_km)

    ns_km = (box.max_latitude - box.min_latitude) * _km_per_degree_lat()
    ew_km = (box.max_longitude - box.min_longitude) * _km_per_degree_lon(lat)

    assert ns_km == pytest.approx(size_km, rel=1e-6)
    assert ew_km == pytest.approx(size_km, rel=1e-6)


def test_centre_sits_in_the_middle() -> None:
    lat, lon = 41.80, 1.25
    box = square_bounding_box(lat, lon, 10.0)

    assert (box.min_latitude + box.max_latitude) / 2 == pytest.approx(lat)
    assert (box.min_longitude + box.max_longitude) / 2 == pytest.approx(lon)


def test_box_widens_in_degrees_towards_the_poles() -> None:
    near_equator = square_bounding_box(0.0, 0.0, 10.0)
    far_north = square_bounding_box(70.0, 0.0, 10.0)

    equator_span = near_equator.max_longitude - near_equator.min_longitude
    north_span = far_north.max_longitude - far_north.min_longitude

    assert north_span > equator_span


def test_antimeridian_crossing_splits_into_two_ranges() -> None:
    box = square_bounding_box(0.0, 179.9, 100.0)

    assert len(box.lon_ranges) == 2
    assert box.lon_ranges[0][1] == 180.0
    assert box.lon_ranges[1][0] == -180.0


def test_latitude_is_clamped_at_the_pole() -> None:
    box = square_bounding_box(89.999, 10.0, 50.0)

    assert box.max_latitude == 90.0
    assert box.lon_ranges == [(-180.0, 180.0)]


def test_single_range_when_no_wrap() -> None:
    box = square_bounding_box(41.80, 1.25, 10.0)

    assert box.lon_ranges == [(box.min_longitude, box.max_longitude)]


# --------------------------------------------------------------- parse_bbox ---
# The contract's bbox is longitude-first, the opposite of everything above.


def test_bbox_reads_longitude_first() -> None:
    box = parse_bbox("1.0,41.6,1.6,42.0")

    assert (box.min_longitude, box.max_longitude) == (1.0, 1.6)
    assert (box.min_latitude, box.max_latitude) == (41.6, 42.0)
    assert box.lon_ranges == [(1.0, 1.6)]


def test_bbox_accepts_negative_and_integer_values() -> None:
    box = parse_bbox("-1,-41,2.5,42")

    assert (box.min_longitude, box.min_latitude) == (-1.0, -41.0)
    assert (box.max_longitude, box.max_latitude) == (2.5, 42.0)


@pytest.mark.parametrize(
    "raw, message",
    [
        (None, "required"),
        ("", "required"),
        ("1.0,41.6,1.6", "malformed"),
        ("1.0,41.6,1.6,42.0,3", "malformed"),
        ("a,b,c,d", "malformed"),
        # The contract's pattern admits none of these spellings.
        ("1e2,41.6,1.6,42.0", "malformed"),
        ("+1.0,41.6,1.6,42.0", "malformed"),
        (" 1.0,41.6,1.6,42.0", "malformed"),
        ("1.0, 41.6, 1.6, 42.0", "malformed"),
        (".5,41.6,1.6,42.0", "malformed"),
        # Ordering and range.
        ("1.6,41.6,1.0,42.0", "minLon"),
        ("1.0,42.0,1.6,41.6", "minLat"),
        ("1.0,91.0,1.6,92.0", "latitude"),
        ("-181.0,41.6,1.6,42.0", "longitude"),
    ],
)
def test_bbox_rejects(raw, message: str) -> None:
    with pytest.raises(BboxError, match=message):
        parse_bbox(raw)


def test_degenerate_bbox_is_allowed() -> None:
    """A zero-area box is empty, not malformed."""
    box = parse_bbox("1.0,41.6,1.0,41.6")

    assert box.min_longitude == box.max_longitude
