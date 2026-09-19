"""Rasterise hourly fire perimeters into a grid of first-arrival hours."""

import math

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

CELL_SIZE_M = 100.0  # ELMFIRE runs at 30 m; finer than that adds nothing
M_PER_DEG_LAT = 111_320.0
MAX_CELLS = 2_000_000  # bounds JSON response size (~5-7 bytes/cell) and list materialisation


class GridTooLarge(ValueError):
    pass


def build_arrival_grid(
    hourly: list[tuple[int, BaseGeometry]],
    ignition_lat: float,
    ignition_lon: float,
) -> dict:
    """Return {originLat, originLon, cellDegLat, cellDegLon, arrivalHours}.

    arrivalHours[row][col]: row 0 is the southernmost row, col 0 the westernmost;
    origin is the south-west corner of cell [0][0]. 0 = ignition, None = not reached.
    """
    dlat = CELL_SIZE_M / M_PER_DEG_LAT
    dlon = CELL_SIZE_M / (M_PER_DEG_LAT * math.cos(math.radians(ignition_lat)))

    minx = maxx = ignition_lon
    miny = maxy = ignition_lat
    if hourly:
        bx0, by0, bx1, by1 = shapely.total_bounds([g for _, g in hourly])
        minx, miny, maxx, maxy = min(minx, bx0), min(miny, by0), max(maxx, bx1), max(maxy, by1)

    # Pad by one cell, anchor the grid so the ignition point sits at a cell centre.
    minx -= dlon
    miny -= dlat
    maxx += dlon
    maxy += dlat
    ox = ignition_lon - dlon / 2 - math.ceil((ignition_lon - dlon / 2 - minx) / dlon) * dlon
    oy = ignition_lat - dlat / 2 - math.ceil((ignition_lat - dlat / 2 - miny) / dlat) * dlat
    nx = int(math.ceil((maxx - ox) / dlon))
    ny = int(math.ceil((maxy - oy) / dlat))

    if nx * ny > MAX_CELLS:
        raise GridTooLarge(
            f"grid would have {nx * ny} cells (> {MAX_CELLS}); increase CELL_SIZE_M"
        )

    xs = ox + (np.arange(nx) + 0.5) * dlon
    ys = oy + (np.arange(ny) + 0.5) * dlat
    gx, gy = np.meshgrid(xs, ys)  # shape (ny, nx)
    flat_x, flat_y = gx.ravel(), gy.ravel()

    arrival = np.full(flat_x.shape, -1, dtype=np.int32)
    # Perimeters are nested (hour h contains hour h-1); walk newest->oldest so
    # the smallest hour wins for each cell.
    for hour, geom in sorted(hourly, key=lambda t: t[0], reverse=True):
        inside = shapely.contains_xy(geom, flat_x, flat_y)
        arrival[inside] = hour

    arr = arrival.reshape(ny, nx)
    # The ignition cell is burning from t=0 (also covers NO_SPREAD, which has no polygons).
    ign_col = int((ignition_lon - ox) / dlon)
    ign_row = int((ignition_lat - oy) / dlat)
    if 0 <= ign_row < ny and 0 <= ign_col < nx:
        arr[ign_row, ign_col] = 0
    # Object array + tolist() is ~10x faster than a Python comprehension at 2M cells.
    obj = arr.astype(object)
    obj[arr < 0] = None
    rows: list[list[int | None]] = obj.tolist()

    return {
        "originLat": float(oy),
        "originLon": float(ox),
        "cellDegLat": dlat,
        "cellDegLon": dlon,
        "arrivalHours": rows,
    }
