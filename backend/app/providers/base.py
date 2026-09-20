"""Asset provider interface and health status tracking.

Trimmed from the decision layer's provider layer. Only the asset side survived
the port: fires come from a seed file and spread comes from Deepfire directly,
so the ``FireProvider``/``SpreadProvider`` interfaces and the ``DATA_MODE``
selection machinery had nothing left to select between.

``ProviderStatus`` is what ``GET /api/health`` reports per upstream.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

from app.engine.contracts import Asset

BBox = tuple[float, float, float, float]  # minLon, minLat, maxLon, maxLat (EPSG:4326)


class ProviderError(RuntimeError):
    """A data provider failed (network, validation, upstream error)."""


@dataclass
class ProviderStatus:
    """Health metadata surfaced by ``GET /api/health``."""

    source: str
    available: bool = True
    last_fetch: str | None = None
    error: str | None = None

    def record_ok(self) -> None:
        self.available = True
        self.error = None
        self.last_fetch = datetime.now(UTC).isoformat()

    def record_error(self, exc: Exception) -> None:
        self.available = False
        self.error = f"{exc.__class__.__name__}: {exc}"


class _StatusMixin:
    """Tracks last fetch/error for health reporting."""

    def __init__(self, source: str) -> None:
        self.status = ProviderStatus(source=source)


class AssetProvider(ABC, _StatusMixin):
    """Source of the values-at-risk asset register."""

    @abstractmethod
    def get_assets(self, bbox: BBox) -> list[Asset]: ...

    def fetch_assets(self, bbox: BBox) -> list[Asset]:
        try:
            assets = self.get_assets(bbox)
        except Exception as exc:
            self.status.record_error(exc)
            raise
        self.status.record_ok()
        return assets
