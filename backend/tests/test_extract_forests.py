"""The pure parts of extract_forests.py: value cleanup, area, row mapping."""

import json
import re
from math import isclose, radians, sin
from pathlib import Path

import pytest
from shapely.geometry import shape

from extract_forests import EARTH_RADIUS_M, FIELDS, _area_ha, _clean, extract

SCHEMA = Path(__file__).resolve().parent.parent / "db" / "init" / "02_forests.sql"


def _ring(min_lon, min_lat, max_lon, max_lat):
    return [
        [min_lon, min_lat], [max_lon, min_lat],
        [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat],
    ]


def _multipolygon(*rings):
    """One polygon: the first ring is the outline, the rest are holes."""
    return {"type": "MultiPolygon", "coordinates": [list(rings)]}


def _feature(**overrides):
    properties = {
        "localid": "ID.AM.forest.1",
        "name_text": "OBAGA I SOLANA",
        "forest_cup": "61",
        "forest_elenc": "1026",
        "forest_conveni": False,
        "forest_ordenacio": True,
        "forest_certificacio": "No",
        "versionid": "20250714",
    }
    properties.update(overrides)
    return {
        "geometry": _multipolygon(_ring(1.0, 41.0, 1.2, 41.1)),
        "properties": properties,
    }


def _exact_rectangle_ha(min_lon, min_lat, max_lon, max_lat):
    """A lat/lon rectangle on a sphere: R^2 * dlon * (sin lat2 - sin lat1).

    Owes nothing to the projection _area_ha uses, so it is an independent check.
    """
    return (
        EARTH_RADIUS_M ** 2
        * radians(max_lon - min_lon)
        * (sin(radians(max_lat)) - sin(radians(min_lat)))
    ) / 10_000


@pytest.mark.parametrize(
    "value, expected",
    [
        ("61", "61"),
        ("Sistema de Certificació PEFC", "Sistema de Certificació PEFC"),
        ("", None),
        ("No", None),
        (None, None),
    ],
)
def test_clean_maps_both_spellings_of_nothing_to_null(value, expected):
    assert _clean(value) == expected


def test_area_matches_the_exact_spherical_rectangle():
    box = (1.0, 41.0, 1.2, 41.1)
    computed = _area_ha(shape(_multipolygon(_ring(*box))))

    # Loose by design: the rectangle has four vertices, so its edges are
    # straight in the projection instead of following the parallels exactly.
    assert isclose(computed, _exact_rectangle_ha(*box), rel_tol=1e-3)


def test_area_subtracts_holes():
    outer, hole = _ring(1.0, 41.0, 1.2, 41.1), _ring(1.05, 41.02, 1.10, 41.07)
    expected = _exact_rectangle_ha(1.0, 41.0, 1.2, 41.1) - _exact_rectangle_ha(
        1.05, 41.02, 1.10, 41.07
    )

    assert isclose(_area_ha(shape(_multipolygon(outer, hole))), expected, rel_tol=1e-3)


def test_row_carries_every_field_and_nothing_else():
    (row,) = extract({"features": [_feature()]})

    assert list(row) == FIELDS


def test_row_maps_the_source_attributes():
    (row,) = extract({"features": [_feature()]})

    assert row["forest_id"] == "ID.AM.forest.1"
    assert row["name"] == "OBAGA I SOLANA"
    assert row["cup_code"] == "61"
    assert row["elenc_code"] == "1026"
    # Written the way Postgres reads a boolean out of a CSV.
    assert (row["has_agreement"], row["has_management_plan"]) == ("false", "true")
    assert row["certification"] is None
    assert row["version_id"] == "20250714"


def test_row_describes_the_geometry_it_carries():
    (row,) = extract({"features": [_feature()]})

    assert (row["min_longitude"], row["min_latitude"]) == (1.0, 41.0)
    assert (row["max_longitude"], row["max_latitude"]) == (1.2, 41.1)
    # The point is inside the forest, not merely inside its envelope.
    assert shape(json.loads(row["geometry"])).covers(
        shape({"type": "Point", "coordinates": [row["longitude"], row["latitude"]]})
    )


def test_uncatalogued_forest_has_no_cup_or_elenc_code():
    (row,) = extract({"features": [_feature(forest_cup="No", forest_elenc="No")]})

    assert (row["cup_code"], row["elenc_code"]) == (None, None)


def test_fields_match_the_table_the_csv_is_copied_into():
    """setup_db.sh COPYs with HEADER MATCH, which needs both to line up."""
    body = re.search(
        r"CREATE TABLE IF NOT EXISTS protection\.forest_areas \((.*?)\n\);",
        SCHEMA.read_text(encoding="utf-8"),
        re.S,
    ).group(1)
    columns = [
        line.split()[0]
        for line in body.splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]

    assert columns == FIELDS
