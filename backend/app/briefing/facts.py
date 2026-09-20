"""Build the structured facts object for briefings (spec §8.2).

This JSON is the ONLY information the LLM receives — every number and name
in a briefing must trace back to it. Times are rendered in Europe/Madrid.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.engine.contracts import Fire, SpreadForecast
from app.engine.scoring import ScoredResult

MADRID = ZoneInfo("Europe/Madrid")


def _local(dt: datetime | None) -> str | None:
    """ISO timestamp converted to Europe/Madrid local time."""
    if dt is None:
        return None
    return dt.astimezone(MADRID).isoformat()


def build_facts(
    fire: Fire,
    forecast: SpreadForecast,
    result: ScoredResult,
    sensitivity_label: str,
    top_n: int = 5,
) -> dict[str, Any]:
    """Structured facts from a scored result. All strings are sanitised."""
    threatened = [a for a in result.assets if a.risk > 0]
    top = threatened[:top_n]
    mean_conf = (
        round(sum(a.confidence for a in threatened) / len(threatened), 2) if threatened else 0.0
    )
    return {
        "fire": {
            "fire_id": fire.fire_id,
            "name": fire.name,
            "reference_time": fire.detected_at.isoformat(),
            "reference_time_local": _local(fire.detected_at),
            "model": forecast.model,
        },
        "horizon_minutes": result.summary.horizon_minutes,
        "total_assets": len(result.assets),
        "threatened_assets": len(threatened),
        "counts_by_tier": result.summary.by_tier,
        "threatened_by_type": result.summary.threatened_by_type,
        "total_value_at_risk": result.summary.total_value_at_risk,
        "mean_confidence": mean_conf,
        "sensitivity_label": sensitivity_label,
        "top_assets": [
            {
                "rank": a.rank,
                "asset_id": a.asset_id,
                "name": a.name,
                "asset_type": a.asset_type,
                "value": a.value,
                "vulnerability": a.vulnerability,
                "eta_minutes": a.eta_minutes,
                "reached_at": _local(a.reached_at),
                "confidence": a.confidence,
                "risk": round(a.risk, 4),
                "main_driver": a.main_driver,
            }
            for a in top
        ],
    }
