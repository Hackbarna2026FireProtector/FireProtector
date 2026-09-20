"""The /api routes, without a database, Deepfire or Overpass.

Replaces the decision layer's Flask API tests. Everything expensive is faked by
pre-seeding a bundle: that is the one object the analysis routes read, so
seeding it exercises the whole request path -- routing, threadpool hand-off,
serialisation -- with no upstream at all.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from app.decision import bundle as bundle_mod
from app.decision.bundle import Bundle
from app.decision.scenarios import Scenario
from app.engine.contracts import _reproject, parse_assets, parse_spread
from app.engine.exposure import compute_exposure
from app.main import create_app

IGNITION = (1.25, 41.80)
SCENARIO_ID = "test-api-001"


def _ring(km: float) -> list[list[float]]:
    d = km / 111.0
    x, y = IGNITION
    return [[x - d, y - d], [x + d, y - d], [x + d, y + d], [x - d, y + d], [x - d, y - d]]


def _scenario() -> Scenario:
    return Scenario(
        scenario_id=SCENARIO_ID,
        name="Test Scenario",
        description="Synthetic, for tests.",
        ignition_point=Point(*IGNITION),
        declared_at=datetime(2026, 9, 19, 14, 0, tzinfo=UTC),
    )


def _forecast() -> Any:
    return parse_spread(
        {
            "type": "FeatureCollection",
            "fire_id": SCENARIO_ID,
            "reference_time": "2026-09-19T14:00:00Z",
            "generated_at": "2026-09-19T14:00:00Z",
            "model": "deepfire-elmfire",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [_ring(1.0)]},
                    "properties": {"eta_minutes": 60, "confidence": 1.0},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [_ring(3.0)]},
                    "properties": {"eta_minutes": 240, "confidence": 0.3},
                },
            ],
        }
    )


def _assets() -> Any:
    def feat(aid: str, atype: str, name: str, value: float, vuln: float, src: str, xy):
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": list(xy)},
            "properties": {
                "asset_id": aid,
                "asset_type": atype,
                "name": name,
                "value": value,
                "vulnerability": vuln,
                "source": src,
            },
        }

    return parse_assets(
        {
            "type": "FeatureCollection",
            "features": [
                feat("osm-node-1", "hospital", "Hospital de Prova", 95, 0.6, "osm", (1.2510, 41.8005)),
                feat("asset-2", "residential", "residential", 45, 0.7, "INSPIRE", (1.2530, 41.8020)),
                feat("asset-3", "shed", "residential", 15, 0.9, "INSPIRE", (1.2700, 41.8200)),
            ],
        }
    )


@pytest.fixture()
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def seeded(monkeypatch: pytest.MonkeyPatch) -> Bundle:
    """A bundle in memory, and a scenario the router can resolve to it."""
    scenario = _scenario()
    forecast = _forecast()
    assets = _assets()
    b = Bundle(
        scenario=scenario,
        forecast=forecast,
        assets=assets,
        exposures=compute_exposure(forecast, assets, _reproject(scenario.ignition_point)),
        built_at=datetime.now(UTC),
        from_disk=True,
        facilities_error=None,
    )
    monkeypatch.setattr(
        "app.decision.scenarios.load_scenarios", lambda: {SCENARIO_ID: scenario}
    )
    monkeypatch.setitem(bundle_mod._bundles, SCENARIO_ID, b)
    yield b
    bundle_mod._bundles.pop(SCENARIO_ID, None)


# ------------------------------------------------------------------ meta ----


def test_config_defaults_covers_every_slider(client: TestClient) -> None:
    body = client.get("/api/config/defaults").json()
    assert set(body["parameters"]) == {
        "tau",
        "w_value",
        "w_conf",
        "w_vuln",
        "w_urgency",
        "horizon",
    }
    assert body["parameters"]["tau"]["default"] == 90.0
    assert body["parameters"]["tau"]["min"] < body["parameters"]["tau"]["max"]


def test_scenarios_carry_no_detection_time_or_status(client: TestClient) -> None:
    """A scenario is hypothetical: claiming either would be a lie. CONTEXT.md."""
    body = client.get("/api/scenarios").json()
    assert body["scenarios"], "the seed file should define at least one"
    for s in body["scenarios"]:
        assert set(s) == {
            "scenario_id",
            "name",
            "description",
            "ignition_point",
            "declared_at",
        }


def test_unknown_scenario_is_404(client: TestClient) -> None:
    assert client.get("/api/scenarios/nope/spread").status_code == 404


# -------------------------------------------------------------- analysis ----


def test_spread_is_the_contract_shape(client: TestClient, seeded: Bundle) -> None:
    body = client.get(f"/api/scenarios/{SCENARIO_ID}/spread").json()
    assert body["type"] == "FeatureCollection"
    assert body["scenario_id"] == SCENARIO_ID
    etas = [f["properties"]["eta_minutes"] for f in body["features"]]
    assert etas == sorted(etas), "contours go on the wire in arrival order"
    # Reprojected back to degrees, not left in EPSG:25831 metres.
    lon, lat = body["features"][0]["geometry"]["coordinates"][0][0]
    assert 0 < lon < 4 and 40 < lat < 43


def test_score_ranks_and_tiers(client: TestClient, seeded: Bundle) -> None:
    body = client.post(f"/api/scenarios/{SCENARIO_ID}/score", json={}).json()
    props = [f["properties"] for f in body["features"]]
    assert [p["rank"] for p in props] == sorted(p["rank"] for p in props)
    # The hospital is worth most and sits nearest the ignition: it leads.
    assert props[0]["asset_id"] == "osm-node-1"
    assert props[0]["risk"] > props[-1]["risk"]
    assert set(body["summary"]) >= {"by_tier", "threatened_by_type", "total_value_at_risk"}


def test_score_reports_whether_the_named_layer_arrived(
    client: TestClient, seeded: Bundle
) -> None:
    """An empty ranked list and a missing Overpass must not look alike."""
    body = client.post(f"/api/scenarios/{SCENARIO_ID}/score", json={}).json()
    assert body["named_layer"] == {"available": True, "count": 1, "error": None}

    bundle_mod._bundles[SCENARIO_ID] = Bundle(
        **{**seeded.__dict__, "facilities_error": "ProviderError: every mirror failed"}
    )
    body = client.post(f"/api/scenarios/{SCENARIO_ID}/score", json={}).json()
    assert body["named_layer"]["available"] is False
    assert "mirror" in body["named_layer"]["error"]


def test_score_rejects_out_of_range_parameters(client: TestClient, seeded: Bundle) -> None:
    """422 becomes 400 with the contract's error envelope, as errors.py does
    for every route — the decision layer inherits that rather than answering in
    FastAPI's own shape."""
    r = client.post(f"/api/scenarios/{SCENARIO_ID}/score", json={"tau": 10_000})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"


def test_sensitivity_reports_robustness(client: TestClient, seeded: Bundle) -> None:
    body = client.post(f"/api/scenarios/{SCENARIO_ID}/sensitivity", json={}).json()
    assert body["robustness"] in {"robust", "moderate", "sensitive"}
    assert body["most_sensitive_parameter"]
    assert body["perturbations"]


def test_briefing_falls_back_to_templates_without_a_key(
    client: TestClient, seeded: Bundle
) -> None:
    body = client.post(f"/api/scenarios/{SCENARIO_ID}/briefing", json={"top_n": 2}).json()
    assert set(body["briefing"]) == {"en", "es", "ca"}
    assert body["source"] == "template"
    assert body["verified"] is True


def test_refresh_drops_the_in_memory_bundle(client: TestClient, seeded: Bundle) -> None:
    assert SCENARIO_ID in bundle_mod._bundles
    assert client.post(f"/api/scenarios/{SCENARIO_ID}/refresh").json()["refreshed"] is True
    assert SCENARIO_ID not in bundle_mod._bundles


# ------------------------------------------------------- the contract ------


def test_the_contract_routes_are_untouched(client: TestClient) -> None:
    """/api must not have moved or shadowed anything at the root."""
    paths = set(client.app.openapi()["paths"])
    assert "/assets" in paths
    assert "/fire/arrival-grid" in paths
    assert not any(p.startswith("/api/assets") and p == "/api/assets" for p in paths)
