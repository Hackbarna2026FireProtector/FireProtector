"""Exposure engine tests (spec §11: exposure)."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from shapely.geometry import Point, Polygon

from app.engine.contracts import Asset, Contour, SpreadForecast
from app.engine.exposure import compute_exposure

REF = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)


def _square(cx: float, cy: float, half: float) -> Polygon:
    return Polygon(
        [
            (cx - half, cy - half),
            (cx + half, cy - half),
            (cx + half, cy + half),
            (cx - half, cy + half),
        ]
    )


def _forecast(
    etas: list[int], halfs: list[float], confs: list[float] | None = None
) -> SpreadForecast:
    confs = confs or [0.9 - 0.05 * i for i in range(len(etas))]
    contours = [
        Contour(eta_minutes=e, confidence=c, geometry=_square(0, 0, h))
        for e, h, c in zip(etas, halfs, confs, strict=True)
    ]
    return SpreadForecast(
        fire_id="f", reference_time=REF, generated_at=REF, model="t", contours=contours
    )


def _asset(aid: str, x: float, y: float) -> Asset:
    return Asset(
        asset_id=aid,
        asset_type="school",
        name=aid,
        value=50.0,
        vulnerability=0.5,
        source="t",
        geometry=Point(x, y),
    )


def test_asset_inside_zero_contour_eta_zero() -> None:
    f = _forecast([0, 60], [500, 2000])
    res = compute_exposure(f, [_asset("a", 0, 0)], Point(0, 0))
    assert res[0].eta_minutes == 0.0
    assert res[0].confidence == f.contours[0].confidence


def test_downwind_reached_before_upwind() -> None:
    # Nested squares: downwind asset inside the 60-min contour, upwind inside 120.
    f = _forecast([0, 60, 120], [500, 2000, 5000])
    res = compute_exposure(f, [_asset("near", 1000, 0), _asset("far", 4000, 0)], Point(0, 0))
    assert res[0].eta_minutes is not None and res[1].eta_minutes is not None
    assert res[0].eta_minutes < res[1].eta_minutes


def test_outside_all_contours_not_reached() -> None:
    f = _forecast([0, 60], [500, 2000])
    res = compute_exposure(f, [_asset("far", 99999, 0)], Point(0, 0))
    assert res[0].eta_minutes is None
    assert res[0].confidence == 0.0
    assert res[0].reached_at is None


def test_interpolated_eta_between_bounding_contours() -> None:
    f = _forecast([0, 60], [500, 2000])
    res = compute_exposure(f, [_asset("mid", 1200, 0)], Point(0, 0))
    assert res[0].eta_minutes is not None
    assert 0.0 < res[0].eta_minutes < 60.0


def test_reached_at_is_reference_plus_eta() -> None:
    f = _forecast([0], [500])
    res = compute_exposure(f, [_asset("a", 0, 0)], Point(0, 0))
    assert res[0].reached_at == REF


def test_polygon_asset_earliest_touch() -> None:
    # Square asset footprint overlapping the edge of the 60-min contour only.
    f = _forecast([0, 60], [500, 2000])
    footprint = _square(2100, 0, 150)  # spans x in [1950, 2250]; contour edge at 2000
    asset = Asset("poly", "hospital", "P", 90, 0.5, "t", footprint)
    res = compute_exposure(f, [asset], Point(0, 0))
    assert res[0].eta_minutes is not None
    assert res[0].eta_minutes <= 60.0


def test_non_nested_contours_min_eta_wins() -> None:
    # Two overlapping, non-nested contours; asset is inside both.
    contours = [
        Contour(eta_minutes=90, confidence=0.5, geometry=_square(1000, 0, 1500)),
        Contour(eta_minutes=30, confidence=0.8, geometry=_square(-1000, 0, 1500)),
    ]
    f = SpreadForecast("f", REF, REF, "t", contours)
    res = compute_exposure(f, [_asset("a", 0, 0)], Point(0, 0))
    assert res[0].eta_minutes is not None
    assert res[0].eta_minutes <= 30.0
    assert res[0].confidence == 0.8


def test_empty_inputs() -> None:
    f = _forecast([], [])
    assert compute_exposure(f, [_asset("a", 0, 0)], Point(0, 0))[0].eta_minutes is None
    assert compute_exposure(_forecast([0], [500]), [], Point(0, 0)) == []


def test_asset_exactly_on_boundary() -> None:
    f = _forecast([60], [2000])
    res = compute_exposure(f, [_asset("edge", 2000, 0)], Point(0, 0))
    assert res[0].eta_minutes is not None
    assert res[0].eta_minutes <= 60.0


def test_performance_2000_assets_20_contours() -> None:
    import random

    rng = random.Random(1)
    contours = [
        Contour(eta_minutes=i * 20, confidence=0.9, geometry=_square(0, 0, 500 + i * 500))
        for i in range(20)
    ]
    f = SpreadForecast("f", REF, REF, "t", contours)
    assets = [
        _asset(f"a{i}", rng.uniform(-15000, 15000), rng.uniform(-15000, 15000)) for i in range(2000)
    ]
    start = time.perf_counter()
    res = compute_exposure(f, assets, Point(0, 0))
    elapsed = time.perf_counter() - start
    assert len(res) == 2000
    assert elapsed < 1.5  # spec target < 1 s; 1.5 s guards slow CI machines
