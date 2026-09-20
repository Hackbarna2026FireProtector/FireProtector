"""Briefing tests: validator checks, service fallback/retry, template output."""

from __future__ import annotations

from typing import Any

from app.briefing.facts import build_facts
from app.briefing.service import generate_briefing
from app.briefing.templates import template_briefing
from app.briefing.validator import validate_briefing
from app.decision_config import Config
from app.engine.exposure import compute_exposure
from app.engine.scoring import ScoreParams, score_assets
from app.engine.sensitivity import sensitivity
from app.engine.contracts import Fire, parse_assets, parse_spread, _reproject

from datetime import UTC, datetime

from shapely.geometry import Point

# A minimal scenario built through the contract parsers rather than from a
# provider: the decision layer's mock provider did not survive the port, and
# these tests only need *some* scored result whose facts the validator can be
# held against.
SCENARIO_ID = "test-scenario-001"
_IGNITION = (1.25, 41.80)


def _ring(km: float) -> list[list[float]]:
    """Square around the ignition, roughly `km` across, in degrees."""
    d = km / 111.0
    x, y = _IGNITION
    return [[x - d, y - d], [x + d, y - d], [x + d, y + d], [x - d, y + d], [x - d, y - d]]


def _bundle() -> tuple[Fire, Any, list, list]:
    forecast = parse_spread(
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
                    "geometry": {"type": "Polygon", "coordinates": [_ring(2.5)]},
                    "properties": {"eta_minutes": 180, "confidence": 0.6},
                },
            ],
        }
    )
    assets = parse_assets(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1.2510, 41.8005]},
                    "properties": {
                        "asset_id": "osm-node-1",
                        "asset_type": "hospital",
                        "name": "Hospital de Prova",
                        "value": 95,
                        "vulnerability": 0.6,
                        "source": "osm",
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1.2600, 41.8100]},
                    "properties": {
                        "asset_id": "osm-node-2",
                        "asset_type": "school",
                        "name": "Escola de Prova",
                        "value": 80,
                        "vulnerability": 0.7,
                        "source": "osm",
                    },
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [1.2450, 41.7950]},
                    "properties": {
                        "asset_id": "asset-3",
                        "asset_type": "storageTank",
                        "name": "residential",
                        "value": 75,
                        "vulnerability": 0.9,
                        "source": "INSPIRE",
                    },
                },
            ],
        }
    )
    fire = Fire(
        fire_id=SCENARIO_ID,
        name="Test Scenario",
        ignition_point=_reproject(Point(*_IGNITION)),
        detected_at=datetime(2026, 9, 19, 14, 0, tzinfo=UTC),
        status="scenario",
    )
    exposures = compute_exposure(forecast, assets, fire.ignition_point)
    return fire, forecast, assets, exposures


def _facts() -> dict[str, Any]:
    fire, forecast, assets, exposures = _bundle()
    result = score_assets(assets, exposures, ScoreParams())
    sens = sensitivity(assets, exposures, ScoreParams())
    return build_facts(fire, forecast, result, sens.robustness, top_n=3)


def test_template_briefing_passes_validator() -> None:
    """The fallback must be valid by construction in all three languages."""
    facts = _facts()
    assert validate_briefing(template_briefing(facts), facts) == []


def test_validator_rejects_missing_language() -> None:
    issues = validate_briefing({"en": "ok", "es": "bien"}, _facts())
    assert any("ca" in i for i in issues)


def test_validator_rejects_hallucinated_number() -> None:
    facts = _facts()
    payload = {
        "en": "The fire threatens 999 assets within the forecast.",
        "es": "El fuego amenaza 999 activos.",
        "ca": "El foc amenaça 999 actius.",
    }
    assert any("numeric[en]" in i for i in validate_briefing(payload, facts))


def test_validator_rejects_wrong_language() -> None:
    facts = _facts()
    payload = {
        "en": "The fire threatens assets in the forecast perimeter with high confidence.",
        "es": "The fire threatens assets in the forecast perimeter with high confidence.",
        "ca": "The fire threatens assets in the forecast perimeter with high confidence.",
    }
    issues = validate_briefing(payload, facts)
    assert any("language[es]" in i for i in issues)
    assert any("language[ca]" in i for i in issues)


def test_validator_rejects_scope_violation() -> None:
    facts = _facts()
    payload = {
        "en": "Evacuation ordered for all towns in the area.",
        "es": "Evacuación ordenada.",
        "ca": "Evacuació ordenada.",
    }
    assert any("scope[en]" in i for i in validate_briefing(payload, facts))


def test_validator_rejects_overlong() -> None:
    facts = _facts()
    payload = {"en": "word " * 160, "es": "fuego", "ca": "foc"}
    assert any("length[en]" in i for i in validate_briefing(payload, facts))


def test_service_template_when_no_key() -> None:
    out = generate_briefing(_facts(), Config(nebius_api_key=""))
    assert out["source"] == "template"
    assert out["verified"] is True
    assert set(out["briefing"]) == {"en", "es", "ca"}


def test_service_llm_success(monkeypatch) -> None:
    facts = _facts()
    valid = template_briefing(facts)
    monkeypatch.setattr("app.briefing.service.call_llm", lambda *a, **k: valid)
    out = generate_briefing(facts, Config(nebius_api_key="key"))
    assert out["source"] == "llm"
    assert out["briefing"]["en"] == valid["en"]


def test_service_retries_then_falls_back(monkeypatch) -> None:
    facts = _facts()
    bad = {"en": "Evacuation ordered.", "es": "Evacuación.", "ca": "Evacuació."}
    calls = []
    monkeypatch.setattr(
        "app.briefing.service.call_llm",
        lambda f, c, issues=None, **k: (calls.append(issues), bad)[1],
    )
    out = generate_briefing(facts, Config(nebius_api_key="key"))
    assert len(calls) == 2  # initial + one retry with issues
    assert calls[1] is not None and calls[1] != []
    assert out["source"] == "template"
    assert out["issues"]  # validator issues surfaced


def test_service_llm_error_falls_back(monkeypatch) -> None:
    from app.briefing.llm import LLMError

    def boom(*a: Any, **k: Any) -> dict[str, str]:
        raise LLMError("timeout")

    monkeypatch.setattr("app.briefing.service.call_llm", boom)
    out = generate_briefing(_facts(), Config(nebius_api_key="key"))
    assert out["source"] == "template"
    assert "llm_error" in out["issues"][0]
