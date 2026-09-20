"""Exposure: join arrival-time contours to assets -> ETA + confidence.

Per asset (spec §7.1):

- ``eta_minutes``: ETA of the smallest-ETA contour intersecting the asset
  (contour ``k``), interpolated between the next-smaller contour ``k-1`` and
  ``k`` by distance::

      eta = eta_{k-1} + (eta_k - eta_{k-1}) * d_prev / (d_prev + d_next)

  where ``d_prev`` / ``d_next`` are distances in metres from the asset's
  representative point to the respective contour *boundaries*. With no
  smaller contour, ``d_prev`` is measured to the fire origin at t=0.
- ``confidence``: confidence of contour ``k`` (0 when not reached).
- ``reached_at``: ``reference_time + eta_minutes``.

Contours are NOT assumed nested; the minimum ETA among intersecting
contours wins. All geometries are EPSG:25831 (metres).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from app.engine.contracts import Asset, Contour, SpreadForecast


@dataclass(frozen=True)
class AssetExposure:
    """Exposure of one asset to a spread forecast."""

    asset_id: str
    eta_minutes: float | None
    confidence: float
    reached_at: datetime | None


def _representative_point(asset_geom: BaseGeometry, origin: BaseGeometry) -> BaseGeometry:
    """Point on the asset footprint nearest the fire origin (metres).

    For polygon assets this is the point the fire reaches first — "any part
    of the footprint counts" means the ETA reflects the nearest approach.
    For point assets it is the point itself. (Spec left the reference point
    undefined; recorded in DECISIONS.md.)
    """
    return nearest_points(asset_geom, origin)[0]


def _interpolated_eta(
    entry_point: BaseGeometry,
    hit: Contour,
    smaller: list[Contour],
    origin: BaseGeometry,
) -> float:
    """Distance-weighted ETA interpolation inside contour ``hit`` (metres)."""
    d_next = entry_point.distance(hit.geometry.boundary)
    if smaller:
        prev = smaller[-1]
        d_prev = entry_point.distance(prev.geometry.boundary)
        eta_prev = float(prev.eta_minutes)
    else:
        d_prev = entry_point.distance(origin)
        eta_prev = 0.0
    span = float(hit.eta_minutes) - eta_prev
    denom = d_prev + d_next
    if denom <= 0:
        return float(hit.eta_minutes)
    return eta_prev + span * (d_prev / denom)


def compute_exposure(
    forecast: SpreadForecast,
    assets: list[Asset],
    ignition_point: BaseGeometry | None = None,
) -> list[AssetExposure]:
    """Compute per-asset ETA/confidence for a forecast.

    Args:
        forecast: validated contours in EPSG:25831.
        assets: validated assets in EPSG:25831.
        ignition_point: fire origin in EPSG:25831; defaults to the smallest
            contour's centroid (per spec fallback).
    """
    contours = sorted(forecast.contours, key=lambda c: c.eta_minutes)
    if ignition_point is None:
        ignition_point = contours[0].geometry.centroid if contours else None

    tree = STRtree([c.geometry for c in contours]) if contours else None

    results: list[AssetExposure] = []
    for asset in assets:
        hit: Contour | None = None
        if tree is not None and not asset.geometry.is_empty:
            for idx in tree.query(asset.geometry, predicate="intersects"):
                contour = contours[int(idx)]
                if hit is None or contour.eta_minutes < hit.eta_minutes:
                    hit = contour

        if hit is None:
            results.append(
                AssetExposure(
                    asset_id=asset.asset_id,
                    eta_minutes=None,
                    confidence=0.0,
                    reached_at=None,
                )
            )
            continue

        if hit.eta_minutes == 0:
            eta = 0.0
        else:
            entry = _representative_point(asset.geometry, ignition_point)
            smaller = [c for c in contours if c.eta_minutes < hit.eta_minutes]
            eta = _interpolated_eta(entry, hit, smaller, ignition_point)
            eta = min(eta, float(hit.eta_minutes))
            if smaller:
                eta = max(eta, float(smaller[-1].eta_minutes))
            if not math.isfinite(eta):
                eta = float(hit.eta_minutes)

        results.append(
            AssetExposure(
                asset_id=asset.asset_id,
                eta_minutes=eta,
                confidence=hit.confidence,
                reached_at=forecast.reference_time + timedelta(minutes=eta),
            )
        )
    return results
