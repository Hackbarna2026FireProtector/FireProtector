"""The arrival-grid rasteriser, checked without Deepfire or a database.

grid.py is the part that can be silently wrong: a grid whose origin or cell
size is off produces a plausible-looking raster that points a fire crew at the
wrong place. Everything here is pure geometry — no network.
"""

import math
from importlib import import_module

import pytest
from fastapi import HTTPException
from shapely.geometry import Point

from fire_spread.grid import CELL_SIZE_M, M_PER_DEG_LAT, GridTooLarge, build_arrival_grid
from fire_spread.router import get_deepfire

LAT, LON = 41.80, 1.25  # La Segarra, Catalonia

# `fire_spread.router` as an attribute is the APIRouter the package re-exports,
# so the module itself has to come out of sys.modules rather than getattr.
router_module = import_module("fire_spread.router")


def circle(radius_m: float, lat: float = LAT, lon: float = LON):
    """A perimeter of roughly `radius_m` around the ignition point."""
    dlat = radius_m / M_PER_DEG_LAT
    return Point(lon, lat).buffer(dlat, quad_segs=32)


def cell_of(grid: dict, lat: float, lon: float) -> tuple[int, int]:
    row = int((lat - grid["originLat"]) / grid["cellDegLat"])
    col = int((lon - grid["originLon"]) / grid["cellDegLon"])
    return row, col


# ------------------------------------------------------------- geometry ---


def test_cells_measure_the_configured_size() -> None:
    grid = build_arrival_grid([(1, circle(500))], LAT, LON)

    ns_m = grid["cellDegLat"] * M_PER_DEG_LAT
    ew_m = grid["cellDegLon"] * M_PER_DEG_LAT * math.cos(math.radians(LAT))

    assert ns_m == pytest.approx(CELL_SIZE_M, rel=1e-9)
    assert ew_m == pytest.approx(CELL_SIZE_M, rel=1e-9)


def test_cells_widen_in_degrees_towards_the_poles() -> None:
    near_equator = build_arrival_grid([], 0.0, 0.0)
    far_north = build_arrival_grid([], 70.0, 0.0)

    assert far_north["cellDegLon"] > near_equator["cellDegLon"]
    assert far_north["cellDegLat"] == pytest.approx(near_equator["cellDegLat"])


def test_origin_is_the_south_west_corner() -> None:
    grid = build_arrival_grid([(1, circle(500))], LAT, LON)

    assert grid["originLat"] < LAT
    assert grid["originLon"] < LON


def test_ignition_sits_at_a_cell_centre() -> None:
    grid = build_arrival_grid([(1, circle(500))], LAT, LON)
    row, col = cell_of(grid, LAT, LON)

    centre_lat = grid["originLat"] + (row + 0.5) * grid["cellDegLat"]
    centre_lon = grid["originLon"] + (col + 0.5) * grid["cellDegLon"]

    assert centre_lat == pytest.approx(LAT, abs=1e-12)
    assert centre_lon == pytest.approx(LON, abs=1e-12)


# ------------------------------------------------------------- arrivals ---


def test_the_earliest_hour_wins_for_nested_perimeters() -> None:
    # Perimeters are nested, so a cell inside the hour-1 circle is also inside
    # every later one. It has to report 1, not the last hour that covered it.
    hourly = [(1, circle(300)), (2, circle(600)), (3, circle(900))]
    grid = build_arrival_grid(hourly, LAT, LON)
    rows = grid["arrivalHours"]

    def at(metres_north: float) -> int | None:
        """The arrival hour that many metres due north of the ignition point."""
        row, col = cell_of(grid, LAT + metres_north / M_PER_DEG_LAT, LON)
        return rows[row][col]

    assert at(200) == 1
    assert at(450) == 2
    assert at(750) == 3
    assert at(950) is None  # the hour-3 perimeter stops at 900 m


def test_perimeters_out_of_order_give_the_same_answer() -> None:
    hourly = [(1, circle(300)), (2, circle(600))]
    assert (
        build_arrival_grid(list(reversed(hourly)), LAT, LON)["arrivalHours"]
        == build_arrival_grid(hourly, LAT, LON)["arrivalHours"]
    )


def test_the_ignition_cell_burns_from_hour_zero() -> None:
    grid = build_arrival_grid([(1, circle(300))], LAT, LON)
    row, col = cell_of(grid, LAT, LON)

    assert grid["arrivalHours"][row][col] == 0


def test_no_spread_still_returns_a_burning_ignition_cell() -> None:
    # A NO_SPREAD simulation comes back with no polygons at all.
    grid = build_arrival_grid([], LAT, LON)
    row, col = cell_of(grid, LAT, LON)

    assert grid["arrivalHours"][row][col] == 0
    assert sum(v is not None for r in grid["arrivalHours"] for v in r) == 1


def test_unreached_cells_are_null_not_a_sentinel() -> None:
    # -1 is the in-memory sentinel; it must never reach the wire, where a
    # consumer would read it as an hour.
    grid = build_arrival_grid([(1, circle(300))], LAT, LON)

    assert all(v is None or v >= 0 for row in grid["arrivalHours"] for v in row)
    assert any(v is None for row in grid["arrivalHours"] for v in row)


def test_rows_run_south_to_north_and_columns_west_to_east() -> None:
    # An offset burn: only the cells north-east of the ignition are reached.
    offset = circle(300, LAT + 600 / M_PER_DEG_LAT, LON + 0.008)
    grid = build_arrival_grid([(1, offset)], LAT, LON)
    rows = grid["arrivalHours"]

    burning = [(r, c) for r, row in enumerate(rows) for c, v in enumerate(row) if v == 1]
    ign_row, ign_col = cell_of(grid, LAT, LON)

    assert burning, "the offset perimeter should cover some cells"
    assert min(r for r, _ in burning) > ign_row
    assert min(c for _, c in burning) > ign_col


def test_the_grid_covers_every_perimeter() -> None:
    grid = build_arrival_grid([(1, circle(1000))], LAT, LON)
    rows = grid["arrivalHours"]

    max_lat = grid["originLat"] + len(rows) * grid["cellDegLat"]
    max_lon = grid["originLon"] + len(rows[0]) * grid["cellDegLon"]
    minx, miny, maxx, maxy = circle(1000).bounds

    assert grid["originLat"] <= miny and max_lat >= maxy
    assert grid["originLon"] <= minx and max_lon >= maxx


def test_an_oversized_grid_is_refused_rather_than_materialised() -> None:
    with pytest.raises(GridTooLarge):
        build_arrival_grid([(1, circle(500_000))], LAT, LON)


# ------------------------------------------------------------ the route ---


@pytest.mark.parametrize("missing", ["DEEPFIRE_CLIENT_ID", "DEEPFIRE_CLIENT_SECRET"])
def test_blank_credentials_are_reported_as_configuration(monkeypatch, missing: str) -> None:
    # docker compose passes these through as empty strings when the host has
    # not set them, so blank has to be caught here rather than surfacing as an
    # opaque 502 from Deepfire's token endpoint.
    monkeypatch.setattr(router_module, "load_dotenv", lambda *a, **kw: False)
    monkeypatch.setenv("DEEPFIRE_CLIENT_ID", "id")
    monkeypatch.setenv("DEEPFIRE_CLIENT_SECRET", "secret")
    monkeypatch.setenv(missing, "   ")
    get_deepfire.cache_clear()

    with pytest.raises(HTTPException) as excinfo:
        get_deepfire()

    assert excinfo.value.status_code == 500
    assert missing in excinfo.value.detail
    get_deepfire.cache_clear()
