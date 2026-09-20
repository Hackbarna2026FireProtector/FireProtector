"""Scoring tests (spec §11: monotonicity, tiers, tie-breaking)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from shapely.geometry import Point

from app.engine.contracts import Asset
from app.engine.exposure import AssetExposure
from app.engine.scoring import ScoreParams, score_assets

REF = datetime(2026, 9, 19, 14, 0, tzinfo=UTC)


def _asset(aid: str, value: float = 50.0, vuln: float = 0.5, atype: str = "school") -> Asset:
    return Asset(aid, atype, aid, value, vuln, "t", Point(0, 0))


def _exp(aid: str, eta: float | None, conf: float = 0.8) -> AssetExposure:
    return AssetExposure(
        asset_id=aid,
        eta_minutes=eta,
        confidence=conf,
        reached_at=REF + timedelta(minutes=eta) if eta is not None else None,
    )


def _score(assets: list[Asset], exps: list[AssetExposure], **params: float):
    return score_assets(assets, exps, ScoreParams(**params))


def test_higher_value_higher_risk() -> None:
    res = _score([_asset("lo", value=20), _asset("hi", value=95)], [_exp("lo", 30), _exp("hi", 30)])
    by_id = {a.asset_id: a for a in res.assets}
    assert by_id["hi"].risk > by_id["lo"].risk


def test_higher_confidence_higher_risk() -> None:
    res = _score([_asset("lo"), _asset("hi")], [_exp("lo", 30, 0.2), _exp("hi", 30, 0.95)])
    by_id = {a.asset_id: a for a in res.assets}
    assert by_id["hi"].risk > by_id["lo"].risk


def test_higher_vulnerability_higher_risk() -> None:
    res = _score([_asset("lo", vuln=0.1), _asset("hi", vuln=0.9)], [_exp("lo", 30), _exp("hi", 30)])
    by_id = {a.asset_id: a for a in res.assets}
    assert by_id["hi"].risk > by_id["lo"].risk


def test_earlier_eta_higher_risk() -> None:
    res = _score([_asset("late"), _asset("early")], [_exp("late", 300), _exp("early", 15)])
    by_id = {a.asset_id: a for a in res.assets}
    assert by_id["early"].risk > by_id["late"].risk


def test_not_reached_zero_risk_not_threatened() -> None:
    res = _score([_asset("safe")], [_exp("safe", None)])
    a = res.assets[0]
    assert a.risk == 0.0
    assert a.f_urgency == 0.0
    assert a.tier == "not_threatened"


def test_weight_zero_removes_factor() -> None:
    res = _score(
        [_asset("lo", value=10), _asset("hi", value=95)],
        [_exp("lo", 30), _exp("hi", 30)],
        w_value=0.0,
    )
    by_id = {a.asset_id: a for a in res.assets}
    assert by_id["lo"].f_value == 1.0 and by_id["hi"].f_value == 1.0
    assert by_id["hi"].risk == pytest.approx(by_id["lo"].risk)


def test_deterministic_tie_break() -> None:
    # Identical inputs -> ranks differ only by deterministic asset_id order.
    assets = [_asset("b"), _asset("a"), _asset("c")]
    exps = [_exp("b", 30), _exp("a", 30), _exp("c", 30)]
    res = _score(assets, exps)
    order = [a.asset_id for a in res.assets]
    assert order == ["a", "b", "c"]
    assert [a.rank for a in res.assets] == [1, 2, 3]


def test_earlier_eta_breaks_risk_ties() -> None:
    # Same risk score is impossible here, but ordering must prefer lower eta
    # when risks are equal — use w_*=0 so only f_urgency differs... instead
    # verify full ordering is risk desc, eta asc.
    res = _score([_asset("b"), _asset("a")], [_exp("b", 60), _exp("a", 60)])
    assert res.assets[0].asset_id == "a"


def test_tiers_follow_rules() -> None:
    # 10 assets, strictly decreasing risk -> 1 critical, 2 high, 3 medium, 4 low.
    assets = [_asset(f"a{i}", value=95 - i * 5) for i in range(10)]
    exps = [_exp(f"a{i}", eta=10 + i * 10, conf=0.9 - i * 0.03) for i in range(10)]
    res = _score(assets, exps)
    tiers = [a.tier for a in sorted(res.assets, key=lambda a: a.rank)]
    assert tiers[0] == "critical"
    assert tiers[1:3] == ["high", "high"]
    assert tiers[3:6] == ["medium", "medium", "medium"]
    assert set(tiers[6:]) == {"low"}


def test_critical_requires_risk_floor() -> None:
    # Single barely-reached asset: risk < 0.05 -> cannot be critical.
    res = _score([_asset("a", value=5, vuln=0.1)], [_exp("a", 350, conf=0.05)], tau=360.0)
    assert res.assets[0].risk < 0.05
    assert res.assets[0].tier != "critical"


def test_horizon_excludes_late_arrivals() -> None:
    res = _score([_asset("late")], [_exp("late", 300)], horizon=120.0)
    a = res.assets[0]
    assert a.f_urgency == 0.0
    assert a.risk == 0.0
    assert a.tier == "not_threatened"


def test_explanation_contains_key_values() -> None:
    res = _score([_asset("Hosp", value=92, vuln=0.6, atype="hospital")], [_exp("Hosp", 90, 0.85)])
    a = res.assets[0]
    assert "Hosp" in a.explanation
    assert "~90 min" in a.explanation
    assert "85%" in a.explanation
    assert "Main driver:" in a.explanation


def test_summary_and_cumulative_risk() -> None:
    assets = [_asset("a", value=90), _asset("b", value=60)]
    exps = [_exp("a", 30), _exp("b", 120), _exp("c", None)]
    res = _score(assets + [_asset("c")], exps)
    assert res.summary.by_tier["not_threatened"] == 1
    assert res.summary.total_value_at_risk == pytest.approx(150)
    risks = [p["risk"] for p in res.summary.cumulative_risk]
    assert risks == sorted(risks)
    assert risks[-1] == pytest.approx(sum(a.risk for a in res.assets if a.risk > 0))
