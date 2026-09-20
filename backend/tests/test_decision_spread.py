"""Turning Deepfire perimeters into arrival contours.

Both cases here come from real responses, not from imagination: a live 24-hour
ELMFIRE run on 2026-09-20 returned 151 perimeters of which 54 were invalid, and
the ensemble split each hour into a certain core plus lower-probability
fringes. Either one, unhandled, breaks something quietly.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.collection import GeometryCollection
from shapely.geometry import LineString

from app.decision.spread import clean_perimeter, perimeters_to_payload
from app.engine.contracts import parse_spread

REF = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)


def _square(size: float = 0.01, x: float = 2.87, y: float = 42.42) -> Polygon:
    return Polygon([(x, y), (x + size, y), (x + size, y + size), (x, y + size)])


# ------------------------------------------------------------- repairing ----


def test_valid_polygon_passes_through() -> None:
    p = _square()
    assert clean_perimeter(p).equals(p)


def test_bowtie_is_repaired() -> None:
    """A ring that crosses itself — "Ring Self-intersection" in the live data."""
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    assert not bowtie.is_valid
    fixed = clean_perimeter(bowtie)
    assert fixed is not None and fixed.is_valid and fixed.area > 0


def test_degenerate_ring_does_not_take_the_forecast_down() -> None:
    """"Too few points in geometry component": a sliver with no area.

    It must be dropped rather than raised, because it arrives alongside 150
    good perimeters and losing all of them to one sliver loses the forecast.
    """
    degenerate = MultiPolygon([_square(), Polygon([(5, 5), (5, 5), (5, 5)])])
    fixed = clean_perimeter(degenerate)
    assert fixed is None or fixed.is_valid


def test_lines_are_dropped_from_a_repaired_collection() -> None:
    """Repair can leave edges behind; a line cannot contain an asset."""
    mixed = GeometryCollection([_square(), LineString([(0, 0), (1, 1)])])
    fixed = clean_perimeter(mixed)
    assert fixed is not None
    assert fixed.geom_type in ("Polygon", "MultiPolygon")


def test_empty_and_none_are_not_perimeters() -> None:
    assert clean_perimeter(None) is None
    assert clean_perimeter(Polygon()) is None


# -------------------------------------------------------------- contours ----


def test_hour_becomes_eta_minutes() -> None:
    payload = perimeters_to_payload("s1", [(3, 1.0, _square())], REF)
    assert payload["features"][0]["properties"]["eta_minutes"] == 180


def test_burn_probability_becomes_confidence() -> None:
    """The ensemble's agreement is the only real confidence signal there is."""
    payload = perimeters_to_payload(
        "s1", [(6, 1.0, _square(0.02)), (6, 0.1, _square(0.005, x=2.90))], REF
    )
    confs = [f["properties"]["confidence"] for f in payload["features"]]
    assert confs == [1.0, 0.1]


@pytest.mark.parametrize("prob", [-0.5, 1.7])
def test_confidence_is_clamped_into_range(prob: float) -> None:
    payload = perimeters_to_payload("s1", [(1, prob, _square())], REF)
    assert 0.0 <= payload["features"][0]["properties"]["confidence"] <= 1.0


def test_unrepairable_perimeters_are_dropped_not_raised() -> None:
    bad = Polygon([(5, 5), (5, 5), (5, 5)])
    payload = perimeters_to_payload("s1", [(1, 1.0, _square()), (2, 1.0, bad)], REF)
    assert len(payload["features"]) == 1


def test_payload_satisfies_the_spread_contract() -> None:
    payload = perimeters_to_payload(
        "s1", [(1, 1.0, _square(0.01)), (2, 0.4, _square(0.02))], REF
    )
    forecast = parse_spread(payload)
    assert [c.eta_minutes for c in forecast.contours] == [60, 120]
    assert forecast.horizon_minutes == 120
