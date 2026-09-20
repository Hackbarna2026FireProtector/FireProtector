"""Risk scoring: per-factor breakdown, tiers, explanations, summary.

Risk model (spec §7.2)::

    f_value   = (value / 100) ^ w_value
    f_conf    = confidence    ^ w_conf
    f_vuln    = vulnerability ^ w_vuln
    f_urgency = exp(-eta_minutes / tau) ^ w_urgency   (0 if not reached)
    risk      = f_value * f_conf * f_vuln * f_urgency   in [0, 1]

``horizon`` is a scoring cap: assets with ``eta > horizon`` are treated as
not threatened (f_urgency = 0). Default horizon = the largest contour ETA.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field

from app.engine.contracts import Asset
from app.engine.exposure import AssetExposure

TIER_ORDER = ["critical", "high", "medium", "low", "not_threatened"]

_CRITICAL_RISK_FLOOR = 0.05

_FACTOR_LABELS = {
    "f_value": "high value",
    "f_conf": "high forecast confidence",
    "f_vuln": "high vulnerability",
    "f_urgency": "imminent arrival",
}
# Deterministic tie-break order when factors are equal.
_FACTOR_PRIORITY = ["f_urgency", "f_value", "f_conf", "f_vuln"]


class ScoreParams(BaseModel):
    """Adjustable scoring parameters (all UI-editable)."""

    tau: float = Field(default=90.0, ge=15.0, le=360.0)
    w_value: float = Field(default=1.0, ge=0.0, le=3.0)
    w_conf: float = Field(default=1.0, ge=0.0, le=3.0)
    w_vuln: float = Field(default=1.0, ge=0.0, le=3.0)
    w_urgency: float = Field(default=1.0, ge=0.0, le=3.0)
    horizon: float | None = Field(default=None, ge=0.0)


@dataclass(frozen=True)
class ScoredAsset:
    """One asset with its full score breakdown."""

    asset_id: str
    name: str
    asset_type: str
    source: str
    value: float
    vulnerability: float
    eta_minutes: float | None
    reached_at: datetime | None
    confidence: float
    f_value: float
    f_conf: float
    f_vuln: float
    f_urgency: float
    risk: float
    rank: int
    tier: str
    main_driver: str
    explanation: str


@dataclass(frozen=True)
class ScoreSummary:
    """Aggregate result for one fire."""

    by_tier: dict[str, int]
    threatened_by_type: dict[str, int]
    total_value_at_risk: float
    horizon_minutes: float
    cumulative_risk: list[dict[str, float]] = field(default_factory=list)


@dataclass(frozen=True)
class ScoredResult:
    assets: list[ScoredAsset]
    summary: ScoreSummary


def _factors(asset: Asset, exposure: AssetExposure, params: ScoreParams) -> dict[str, float]:
    """Compute the four risk factors; f_urgency is 0 beyond the horizon."""
    reached = exposure.eta_minutes is not None and exposure.eta_minutes <= (
        params.horizon if params.horizon is not None else math.inf
    )
    return {
        "f_value": (asset.value / 100.0) ** params.w_value,
        "f_conf": exposure.confidence**params.w_conf,
        "f_vuln": asset.vulnerability**params.w_vuln,
        "f_urgency": math.exp(-(exposure.eta_minutes or 0.0) / params.tau) ** params.w_urgency
        if reached
        else 0.0,
    }


def _main_driver(factors: dict[str, float]) -> str:
    """Strongest factor (max f_* / min -log deficit); deterministic on ties."""
    return min(_FACTOR_PRIORITY, key=lambda f: -math.log(max(factors[f], 1e-12)))


def _explanation(
    asset: Asset, exposure: AssetExposure, factors: dict[str, float], tier: str
) -> str:
    """Deterministic one-sentence explanation built only from computed values."""
    if tier == "not_threatened":
        if exposure.eta_minutes is None:
            return f"{asset.name}: outside all forecast contours — not threatened."
        return f"{asset.name}: arrival beyond the forecast horizon — not threatened."
    pct = round(exposure.confidence * 100)
    eta = round(exposure.eta_minutes or 0.0)
    driver = _FACTOR_LABELS[_main_driver(factors)]
    return (
        f"{asset.name} ({asset.asset_type}, value {asset.value:g}, "
        f"vulnerability {asset.vulnerability:g}): fire expected in ~{eta} min "
        f"(confidence {pct}%). Main driver: {driver}."
    )


def _assign_tiers(scored: list[ScoredAsset]) -> list[ScoredAsset]:
    """Assign tiers to reached assets: critical top 10% (risk>=0.05), high
    next 20%, medium next 30%, low the rest (over risk>0 assets, by rank)."""
    threatened = [a for a in scored if a.risk > 0]
    n = len(threatened)
    tiers: dict[str, str] = {}
    for i, a in enumerate(threatened):
        if i < math.ceil(0.10 * n) and a.risk >= _CRITICAL_RISK_FLOOR:
            tiers[a.asset_id] = "critical"
        elif i < math.ceil(0.30 * n):
            tiers[a.asset_id] = "high"
        elif i < math.ceil(0.60 * n):
            tiers[a.asset_id] = "medium"
        else:
            tiers[a.asset_id] = "low"
    return [
        ScoredAsset(**{**a.__dict__, "tier": tiers.get(a.asset_id, "not_threatened")})
        for a in scored
    ]


def score_assets(
    assets: list[Asset],
    exposures: list[AssetExposure],
    params: ScoreParams,
) -> ScoredResult:
    """Score, rank, tier and explain every asset.

    Args:
        assets: validated assets (EPSG:25831 geometries unused here).
        exposures: matching exposures from ``compute_exposure``.
        params: scoring parameters; ``horizon=None`` means the forecast max.
    """
    exp_by_id = {e.asset_id: e for e in exposures}
    rows: list[ScoredAsset] = []
    for asset in assets:
        exposure = exp_by_id[asset.asset_id]
        factors = _factors(asset, exposure, params)
        risk = math.prod(factors.values())
        rows.append(
            ScoredAsset(
                asset_id=asset.asset_id,
                name=asset.name,
                asset_type=asset.asset_type,
                source=asset.source,
                value=asset.value,
                vulnerability=asset.vulnerability,
                eta_minutes=exposure.eta_minutes,
                reached_at=exposure.reached_at,
                confidence=exposure.confidence,
                f_value=factors["f_value"],
                f_conf=factors["f_conf"],
                f_vuln=factors["f_vuln"],
                f_urgency=factors["f_urgency"],
                risk=risk,
                rank=0,
                tier="not_threatened",
                main_driver=_main_driver(factors),
                explanation="",
            )
        )

    # Deterministic ranking: risk desc, then eta asc, then asset_id.
    rows.sort(
        key=lambda a: (
            -a.risk,
            a.eta_minutes if a.eta_minutes is not None else math.inf,
            a.asset_id,
        )
    )
    ranked = [ScoredAsset(**{**a.__dict__, "rank": i + 1}) for i, a in enumerate(rows)]
    tiered = _assign_tiers(ranked)
    assets_by_id = {a.asset_id: a for a in assets}
    final = [
        ScoredAsset(
            **{
                **a.__dict__,
                "explanation": _explanation(
                    assets_by_id[a.asset_id],
                    exp_by_id[a.asset_id],
                    {
                        "f_value": a.f_value,
                        "f_conf": a.f_conf,
                        "f_vuln": a.f_vuln,
                        "f_urgency": a.f_urgency,
                    },
                    a.tier,
                ),
            }
        )
        for a in tiered
    ]

    horizon = params.horizon
    if horizon is None:
        reached_etas = [a.eta_minutes for a in final if a.eta_minutes is not None]
        horizon = max(reached_etas, default=0.0)

    by_tier = {t: 0 for t in TIER_ORDER}
    by_type: dict[str, int] = {}
    for a in final:
        by_tier[a.tier] += 1
        if a.risk > 0:
            by_type[a.asset_type] = by_type.get(a.asset_type, 0) + 1
    total_value = sum(a.value for a in final if a.risk > 0)

    cumulative = [
        {
            "minute": float(m),
            "risk": sum(a.risk for a in final if a.eta_minutes is not None and a.eta_minutes <= m),
        }
        for m in range(0, int(math.ceil(horizon)) + 1)
    ]

    return ScoredResult(
        assets=final,
        summary=ScoreSummary(
            by_tier=by_tier,
            threatened_by_type=by_type,
            total_value_at_risk=total_value,
            horizon_minutes=horizon,
            cumulative_risk=cumulative,
        ),
    )
