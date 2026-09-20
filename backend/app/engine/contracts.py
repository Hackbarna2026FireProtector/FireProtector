"""Input contract validation and CRS handling.

All payloads on the wire are GeoJSON in EPSG:4326 (lon/lat degrees).
Internally everything is reprojected to EPSG:25831 (ETRS89 / UTM 31N) so
distances are in metres.

Validation rules (contracts/*.openapi.yaml):
- spread contours: ``eta_minutes`` integer >= 0, ``confidence`` in [0, 1],
  geometry Polygon|MultiPolygon, repaired via ``make_valid`` or rejected.
- assets: ``asset_id`` unique, ``value`` in [1, 100], ``vulnerability`` in
  [0, 1], ``name`` sanitised (control chars stripped, 120-char cap).
- a ``crs`` member, if present, must declare EPSG:4326 (RFC 7946 default).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import pyproj
from pydantic import BaseModel, Field, ValidationError, field_validator
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

INPUT_CRS = "EPSG:4326"
METRIC_CRS = "EPSG:25831"

_to_metric = pyproj.Transformer.from_crs(INPUT_CRS, METRIC_CRS, always_xy=True).transform

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_NAME_MAX_LEN = 120


class ContractError(ValueError):
    """A payload violates the spread/assets API contract."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues[:10]))


def sanitize_name(raw: str) -> str:
    """Strip control characters and cap at 120 chars.

    ``name`` is untrusted free text later passed to an LLM — never interpret
    it as instructions.
    """
    cleaned = _CONTROL_CHARS.sub("", raw).strip()
    return cleaned[:_NAME_MAX_LEN]


def _declared_crs_ok(payload: dict[str, Any]) -> bool:
    """A ``crs`` member, if present, must be EPSG:4326 (else True: RFC 7946)."""
    crs = payload.get("crs")
    if crs is None:
        return True
    text = str(crs)
    return "4326" in text or "CRS84" in text or "urn:ogc:def:crs:OGC" in text


def _parse_geometry(raw: Any) -> BaseGeometry:
    """Parse, repair and validate a GeoJSON geometry dict."""
    geom = shape(raw)
    if geom.is_empty:
        raise ContractError(["geometry is empty"])
    if not geom.is_valid:
        geom = make_valid(geom)
        if geom.is_empty or not geom.is_valid:
            raise ContractError(["geometry invalid and could not be repaired"])
    return geom


class _ContourProps(BaseModel):
    eta_minutes: int = Field(ge=0)
    confidence: float = Field(ge=0.0, le=1.0)


class _ContourFeature(BaseModel):
    type: Literal["Feature"]
    geometry: dict[str, Any]
    properties: _ContourProps


class _SpreadPayload(BaseModel):
    type: Literal["FeatureCollection"]
    fire_id: str
    reference_time: datetime
    generated_at: datetime
    model: str
    features: list[_ContourFeature]

    @field_validator("type", mode="before")
    @classmethod
    def _type_present(cls, v: Any) -> Any:
        return v


class _AssetProps(BaseModel):
    asset_id: str = Field(min_length=1)
    asset_type: str = Field(min_length=1)
    name: str = ""
    value: float = Field(ge=1.0, le=100.0)
    vulnerability: float = Field(ge=0.0, le=1.0)
    source: str = ""


class _AssetFeature(BaseModel):
    type: Literal["Feature"]
    geometry: dict[str, Any]
    properties: _AssetProps


class _AssetsPayload(BaseModel):
    type: Literal["FeatureCollection"]
    features: list[_AssetFeature]


@dataclass(frozen=True)
class Contour:
    """One arrival-time contour. ``geometry`` is in EPSG:25831 (metres)."""

    eta_minutes: int
    confidence: float
    geometry: BaseGeometry


@dataclass(frozen=True)
class Asset:
    """One infrastructure asset. ``geometry`` is in EPSG:25831 (metres)."""

    asset_id: str
    asset_type: str
    name: str
    value: float
    vulnerability: float
    source: str
    geometry: BaseGeometry


@dataclass(frozen=True)
class SpreadForecast:
    """Validated arrival-time contour forecast for one fire."""

    fire_id: str
    reference_time: datetime
    generated_at: datetime
    model: str
    contours: list[Contour] = field(default_factory=list)

    @property
    def horizon_minutes(self) -> float:
        """Largest ETA across contours, in minutes (0 for an empty forecast)."""
        return float(max((c.eta_minutes for c in self.contours), default=0))


@dataclass(frozen=True)
class Fire:
    """An active fire as listed by the spread service."""

    fire_id: str
    name: str
    ignition_point: BaseGeometry
    detected_at: datetime
    status: str


def _reproject(geom: BaseGeometry) -> BaseGeometry:
    """Reproject a shapely geometry from EPSG:4326 to EPSG:25831."""
    from shapely.ops import transform

    return transform(_to_metric, geom)


def _validation_issues(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()]


def parse_spread(payload: dict[str, Any]) -> SpreadForecast:
    """Validate a spread-forecast payload; return contours in EPSG:25831.

    Raises ``ContractError`` listing every issue found.
    """
    issues: list[str] = []
    if not _declared_crs_ok(payload):
        raise ContractError(["crs: only EPSG:4326 payloads are accepted"])
    try:
        parsed = _SpreadPayload.model_validate(payload)
    except ValidationError as exc:
        raise ContractError(_validation_issues(exc)) from exc

    contours: list[Contour] = []
    for i, feature in enumerate(parsed.features):
        geom_type = feature.geometry.get("type")
        if geom_type not in ("Polygon", "MultiPolygon"):
            issues.append(f"features[{i}].geometry: type {geom_type} not allowed")
            continue
        try:
            geom = _parse_geometry(feature.geometry)
        except Exception as exc:
            issues.append(f"features[{i}].geometry: {exc}")
            continue
        contours.append(
            Contour(
                eta_minutes=feature.properties.eta_minutes,
                confidence=feature.properties.confidence,
                geometry=_reproject(geom),
            )
        )
    if issues:
        raise ContractError(issues)
    return SpreadForecast(
        fire_id=parsed.fire_id,
        reference_time=parsed.reference_time,
        generated_at=parsed.generated_at,
        model=parsed.model,
        contours=sorted(contours, key=lambda c: c.eta_minutes),
    )


def parse_assets(payload: dict[str, Any]) -> list[Asset]:
    """Validate an asset FeatureCollection; return assets in EPSG:25831.

    Duplicate ``asset_id`` rejects the whole collection.
    """
    issues: list[str] = []
    if not _declared_crs_ok(payload):
        raise ContractError(["crs: only EPSG:4326 payloads are accepted"])
    try:
        parsed = _AssetsPayload.model_validate(payload)
    except ValidationError as exc:
        raise ContractError(_validation_issues(exc)) from exc

    assets: list[Asset] = []
    seen: set[str] = set()
    for i, feature in enumerate(parsed.features):
        props = feature.properties
        if props.asset_id in seen:
            issues.append(f"features[{i}]: duplicate asset_id {props.asset_id!r}")
            continue
        geom_type = feature.geometry.get("type")
        if geom_type not in ("Point", "Polygon", "MultiPolygon"):
            issues.append(f"features[{i}].geometry: type {geom_type} not allowed")
            continue
        try:
            geom = _parse_geometry(feature.geometry)
        except Exception as exc:
            issues.append(f"features[{i}].geometry: {exc}")
            continue
        seen.add(props.asset_id)
        assets.append(
            Asset(
                asset_id=props.asset_id,
                asset_type=props.asset_type,
                name=sanitize_name(props.name),
                value=props.value,
                vulnerability=props.vulnerability,
                source=props.source,
                geometry=_reproject(geom),
            )
        )
    if issues:
        raise ContractError(issues)
    return assets


class _FireModel(BaseModel):
    fire_id: str = Field(min_length=1)
    name: str = ""
    ignition_point: dict[str, Any]
    detected_at: datetime
    status: str = "active"


class _FiresPayload(BaseModel):
    fires: list[_FireModel]


def parse_fires(payload: dict[str, Any]) -> list[Fire]:
    """Validate a ``GET /fires`` response."""
    try:
        parsed = _FiresPayload.model_validate(payload)
    except ValidationError as exc:
        raise ContractError(_validation_issues(exc)) from exc
    fires: list[Fire] = []
    issues: list[str] = []
    for i, fire in enumerate(parsed.fires):
        try:
            geom = _parse_geometry(fire.ignition_point)
            if geom.geom_type != "Point":
                raise ContractError(["ignition_point must be a Point"])
        except Exception as exc:
            issues.append(f"fires[{i}].ignition_point: {exc}")
            continue
        fires.append(
            Fire(
                fire_id=fire.fire_id,
                name=sanitize_name(fire.name),
                ignition_point=_reproject(geom),
                detected_at=fire.detected_at,
                status=fire.status,
            )
        )
    if issues:
        raise ContractError(issues)
    return fires
