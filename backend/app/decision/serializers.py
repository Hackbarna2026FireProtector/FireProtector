"""Serialize domain objects back to EPSG:4326 GeoJSON for API responses.

The engine works in EPSG:25831 because exposure needs distances in metres;
everything that leaves the process goes back to degrees here.
"""

from __future__ import annotations

from typing import Any

import pyproj
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from app.engine.contracts import Asset, Contour, SpreadForecast
from app.engine.scoring import ScoredAsset, ScoredResult
from app.engine.sensitivity import SensitivityResult

_to_wgs = pyproj.Transformer.from_crs("EPSG:25831", "EPSG:4326", always_xy=True).transform


def _wgs(geom: BaseGeometry) -> dict[str, Any]:
    """GeoJSON dict of a metric geometry reprojected to EPSG:4326."""
    return mapping(transform(_to_wgs, geom))


# fire_to_dict is deliberately absent: the engine's Fire carries detected_at
# and status, neither of which is true of a hypothetical ignition. Scenarios
# serialise themselves — see decision/scenarios.py::Scenario.to_dict.


def contour_to_feature(contour: Contour) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": _wgs(contour.geometry),
        "properties": {
            "eta_minutes": contour.eta_minutes,
            "confidence": contour.confidence,
        },
    }


def forecast_to_geojson(forecast: SpreadForecast) -> dict[str, Any]:
    """The §5.1 contract payload shape."""
    return {
        "type": "FeatureCollection",
        "scenario_id": forecast.fire_id,
        "reference_time": forecast.reference_time.isoformat(),
        "generated_at": forecast.generated_at.isoformat(),
        "model": forecast.model,
        "features": [contour_to_feature(c) for c in forecast.contours],
    }


def asset_to_feature(asset: Asset) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": _wgs(asset.geometry),
        "properties": {
            "asset_id": asset.asset_id,
            "asset_type": asset.asset_type,
            "name": asset.name,
            "value": asset.value,
            "vulnerability": asset.vulnerability,
            "source": asset.source,
        },
    }


def assets_to_geojson(assets: list[Asset]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [asset_to_feature(a) for a in assets],
    }


def scored_asset_to_feature(scored: ScoredAsset, asset: Asset) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": _wgs(asset.geometry),
        "properties": {
            "asset_id": scored.asset_id,
            "name": scored.name,
            "asset_type": scored.asset_type,
            "source": scored.source,
            "value": scored.value,
            "vulnerability": scored.vulnerability,
            "eta_minutes": scored.eta_minutes,
            "reached_at": scored.reached_at.isoformat() if scored.reached_at else None,
            "confidence": scored.confidence,
            "f_value": round(scored.f_value, 6),
            "f_conf": round(scored.f_conf, 6),
            "f_vuln": round(scored.f_vuln, 6),
            "f_urgency": round(scored.f_urgency, 6),
            "risk": round(scored.risk, 6),
            "rank": scored.rank,
            "tier": scored.tier,
            "main_driver": scored.main_driver,
            "explanation": scored.explanation,
        },
    }


def scored_result_to_payload(result: ScoredResult, assets: list[Asset]) -> dict[str, Any]:
    """Full ``POST /score`` response: GeoJSON + summary."""
    by_id = {a.asset_id: a for a in assets}
    s = result.summary
    return {
        "type": "FeatureCollection",
        "features": [scored_asset_to_feature(a, by_id[a.asset_id]) for a in result.assets],
        "summary": {
            "by_tier": s.by_tier,
            "threatened_by_type": s.threatened_by_type,
            "total_value_at_risk": s.total_value_at_risk,
            "horizon_minutes": s.horizon_minutes,
            "cumulative_risk": s.cumulative_risk,
        },
    }


def sensitivity_to_payload(result: SensitivityResult) -> dict[str, Any]:
    return {
        "robustness": result.robustness,
        "most_sensitive_parameter": result.most_sensitive_parameter,
        "perturbations": [
            {
                "parameter": p.parameter,
                "multiplier": p.multiplier,
                "top5_overlap": round(p.top5_overlap, 4),
                "top10_overlap": round(p.top10_overlap, 4),
                "kendall_tau": round(p.kendall_tau, 4),
            }
            for p in result.perturbations
        ],
        "rank_ranges": result.rank_ranges,
    }
