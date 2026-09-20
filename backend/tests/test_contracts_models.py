"""Contract validation tests (spec §11: contracts)."""

from __future__ import annotations

import copy

import pytest

from app.engine.contracts import (
    ContractError,
    parse_assets,
    parse_spread,
    sanitize_name,
)


def _spread_payload() -> dict:
    return {
        "type": "FeatureCollection",
        "fire_id": "f1",
        "reference_time": "2026-09-19T14:00:00Z",
        "generated_at": "2026-09-19T14:02:10Z",
        "model": "test",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[1.24, 41.79], [1.26, 41.79], [1.26, 41.81], [1.24, 41.81], [1.24, 41.79]]
                    ],
                },
                "properties": {"eta_minutes": 30, "confidence": 0.8},
            }
        ],
    }


def _asset_payload() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [1.25, 41.80]},
                "properties": {
                    "asset_id": "a1",
                    "asset_type": "hospital",
                    "name": "Hospital",
                    "value": 80,
                    "vulnerability": 0.5,
                    "source": "test",
                },
            }
        ],
    }


def test_spread_valid() -> None:
    f = parse_spread(_spread_payload())
    assert f.fire_id == "f1"
    assert len(f.contours) == 1
    # Geometry was reprojected to metres (UTM coordinates are ~5e5 / 4.6e6).
    x, y = f.contours[0].geometry.centroid.x, f.contours[0].geometry.centroid.y
    assert 300_000 < x < 600_000 and 4_000_000 < y < 5_000_000


def test_spread_missing_field() -> None:
    payload = _spread_payload()
    del payload["model"]
    with pytest.raises(ContractError):
        parse_spread(payload)


def test_spread_confidence_out_of_range() -> None:
    payload = _spread_payload()
    payload["features"][0]["properties"]["confidence"] = 1.4
    with pytest.raises(ContractError):
        parse_spread(payload)


def test_spread_negative_eta() -> None:
    payload = _spread_payload()
    payload["features"][0]["properties"]["eta_minutes"] = -5
    with pytest.raises(ContractError):
        parse_spread(payload)


def test_spread_wrong_crs_rejected() -> None:
    payload = _spread_payload()
    payload["crs"] = {"type": "name", "properties": {"name": "EPSG:3857"}}
    with pytest.raises(ContractError):
        parse_spread(payload)


def test_spread_explicit_4326_crs_accepted() -> None:
    payload = _spread_payload()
    payload["crs"] = {"type": "name", "properties": {"name": "EPSG:4326"}}
    assert len(parse_spread(payload).contours) == 1


def test_spread_invalid_geometry_repaired() -> None:
    # Bowtie (self-intersecting) polygon — make_valid should repair it.
    payload = _spread_payload()
    payload["features"][0]["geometry"]["coordinates"] = [
        [[1.24, 41.79], [1.26, 41.81], [1.26, 41.79], [1.24, 41.81], [1.24, 41.79]]
    ]
    f = parse_spread(payload)
    assert len(f.contours) == 1
    assert not f.contours[0].geometry.is_empty


def test_assets_valid() -> None:
    assets = parse_assets(_asset_payload())
    assert len(assets) == 1
    assert assets[0].asset_id == "a1"


def test_assets_duplicate_id_rejected() -> None:
    payload = _asset_payload()
    dup = copy.deepcopy(payload["features"][0])
    payload["features"].append(dup)
    with pytest.raises(ContractError, match="duplicate"):
        parse_assets(payload)


@pytest.mark.parametrize("field,bad", [("value", 0), ("value", 120), ("vulnerability", 1.5)])
def test_assets_out_of_range(field: str, bad: float) -> None:
    payload = _asset_payload()
    payload["features"][0]["properties"][field] = bad
    with pytest.raises(ContractError):
        parse_assets(payload)


def test_asset_name_sanitized() -> None:
    payload = _asset_payload()
    payload["features"][0]["properties"]["name"] = "  X\x07name\x00  " + "y" * 200
    assets = parse_assets(payload)
    assert len(assets[0].name) == 120
    assert "\x00" not in assets[0].name and "\x07" not in assets[0].name


def test_sanitize_name_caps_length() -> None:
    assert len(sanitize_name("a" * 500)) == 120
    assert sanitize_name("ok") == "ok"


def test_assets_missing_geometry_type_rejected() -> None:
    payload = _asset_payload()
    payload["features"][0]["geometry"] = {
        "type": "LineString",
        "coordinates": [[1.0, 41.0], [1.1, 41.1]],
    }
    with pytest.raises(ContractError):
        parse_assets(payload)
