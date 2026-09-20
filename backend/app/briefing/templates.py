"""Deterministic template briefing fallback (spec §8.6).

Hand-written sentence templates in EN/ES/CA filled strictly from the facts
object — always valid by construction (the validator runs over it in
tests). Strings live in per-language JSON catalogues under ``i18n/`` so the
same mechanism can later translate the whole UI.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

LANGUAGES = ("en", "es", "ca")
_I18N_DIR = Path(__file__).resolve().parent / "i18n"


@lru_cache(maxsize=8)
def _catalogue(lang: str) -> dict[str, str]:
    return json.loads((_I18N_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def _fmt(catalogue: dict[str, str], key: str, **kwargs: Any) -> str:
    return catalogue[key].format(**kwargs)


def _ref_time_local(facts: dict[str, Any]) -> str:
    """HH:MM from the local ISO timestamp in facts."""
    raw = facts.get("fire", {}).get("reference_time_local") or ""
    return raw[11:16] if len(raw) >= 16 else "--:--"


def render_template(facts: dict[str, Any], lang: str) -> str:
    """Render the briefing for one language from the facts object."""
    cat = _catalogue(lang)
    fire = facts.get("fire", {})
    ref_time = _ref_time_local(facts)
    horizon = round(float(facts.get("horizon_minutes", 0)))
    threatened = int(facts.get("threatened_assets", 0))
    total = int(facts.get("total_assets", 0))
    counts = facts.get("counts_by_tier", {})

    if threatened == 0:
        text = _fmt(
            cat,
            "briefing.none",
            ref_time=ref_time,
            fire_name=fire.get("name", ""),
            horizon=horizon,
        )
    else:
        text = _fmt(
            cat,
            "briefing.threatened",
            ref_time=ref_time,
            fire_name=fire.get("name", ""),
            threatened=threatened,
            total=total,
            horizon=horizon,
            critical=counts.get("critical", 0),
            high=counts.get("high", 0),
        )
        items = [
            _fmt(
                cat,
                "briefing.top_item",
                name=a["name"],
                asset_type=a["asset_type"],
                eta=round(float(a["eta_minutes"] or 0)),
                conf=round(float(a["confidence"]) * 100),
            )
            for a in facts.get("top_assets", [])
        ]
        if items:
            text += " " + cat["briefing.top_intro"] + " " + "; ".join(items) + "."

    mean_conf = round(float(facts.get("mean_confidence", 0)) * 100)
    text += " " + _fmt(cat, "briefing.confidence", conf=mean_conf)
    label = cat.get(
        f"briefing.label.{facts.get('sensitivity_label')}", facts.get("sensitivity_label", "")
    )
    text += " " + _fmt(cat, "briefing.sensitivity", label=label)
    return text


def template_briefing(facts: dict[str, Any]) -> dict[str, str]:
    """Deterministic EN/ES/CA briefing texts."""
    return {lang: render_template(facts, lang) for lang in LANGUAGES}
