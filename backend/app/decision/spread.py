"""Deepfire perimeters -> the arrival-contour shape the engine scores against.

An ELMFIRE run returns one perimeter per simulated hour: the area burned within
that many hours of ignition. That *is* an arrival-time contour — the conversion
is ``eta_minutes = hour * 60`` and nothing else. The 100 m arrival grid the
asset-register API serves is derived from these same perimeters, so the raster
is a lossier view of this data rather than a separate source, and scoring reads
the perimeters directly to keep continuous ETAs: quantising to whole hours
would collapse ``exp(-eta/tau)`` into a handful of ties.

``confidence`` is the ensemble's ``burn_probability``. Verified against the
live API on 2026-09-20 with ``ensembleMembers=10``: hours 1..N come back at
1.0, and the final hour carries additional envelopes at lower probabilities —
the fringe only some members reached. An asset inside a 0.1 envelope genuinely
is a less certain casualty than one inside the core, so this is a real scoring
factor rather than a restatement of urgency.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shapely.validation import make_valid

from app.engine.contracts import SpreadForecast, parse_spread

log = logging.getLogger(__name__)

MODEL_NAME = "deepfire-elmfire"

_POLYGONAL = ("Polygon", "MultiPolygon")


def _polygonal_parts(geom: BaseGeometry) -> BaseGeometry | None:
    """Drop anything that is not an area.

    Repairing a self-intersecting perimeter can leave a GeometryCollection with
    the offending edges in it as lines. A line has no area, so it cannot
    contain an asset, and carrying it forward only breaks the next overlay.
    """
    if geom.geom_type in _POLYGONAL:
        return geom
    parts = [g for g in getattr(geom, "geoms", []) if g.geom_type in _POLYGONAL]
    return unary_union(parts) if parts else None


def clean_perimeter(geom: BaseGeometry | None) -> BaseGeometry | None:
    """Make one ELMFIRE perimeter safe to overlay, or None if it cannot be.

    Measured against a live 24-hour run: 54 of 151 perimeters came back invalid
    -- degenerate rings ("too few points in geometry component") and ring
    self-intersections -- and on one of them ``make_valid`` itself raised
    ``IllegalArgumentException: Overlay input is mixed-dimension``. ``buffer(0)``
    repaired that one, so both are tried before a perimeter is given up on.
    """
    if geom is None or geom.is_empty:
        return None
    if geom.is_valid:
        return _polygonal_parts(geom)
    for repair in (make_valid, lambda g: g.buffer(0)):
        try:
            fixed = repair(geom)
        except Exception:  # noqa: BLE001 - try the next repair
            continue
        if fixed is not None and fixed.is_valid and not fixed.is_empty:
            return _polygonal_parts(fixed)
    return None


def perimeters_to_payload(
    scenario_id: str,
    perimeters: list[tuple[int, float, BaseGeometry]],
    reference_time: datetime,
) -> dict[str, Any]:
    """Build the spread-contract payload from ``(hour, probability, geom)``."""
    now = datetime.now(UTC)
    features: list[dict[str, Any]] = []
    dropped = 0
    for hour, probability, geom in perimeters:
        cleaned = clean_perimeter(geom)
        if cleaned is None:
            dropped += 1
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": cleaned.__geo_interface__,
                "properties": {
                    # Hour 0 is the ignition itself; the engine requires a
                    # non-negative integer and treats 0 as "already burning".
                    "eta_minutes": max(0, int(hour) * 60),
                    "confidence": min(1.0, max(0.0, float(probability))),
                },
            }
        )
    if dropped:
        log.warning(
            "scenario %s: dropped %d of %d perimeters that could not be repaired",
            scenario_id,
            dropped,
            len(perimeters),
        )
    return {
        "type": "FeatureCollection",
        "fire_id": scenario_id,
        "reference_time": reference_time.isoformat(),
        "generated_at": now.isoformat(),
        "model": MODEL_NAME,
        "features": features,
    }


def build_forecast(
    scenario_id: str,
    perimeters: list[tuple[int, float, BaseGeometry]],
    reference_time: datetime,
) -> SpreadForecast:
    """Validated forecast in EPSG:25831, ready for the exposure join."""
    return parse_spread(perimeters_to_payload(scenario_id, perimeters, reference_time))
