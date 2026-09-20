"""Sensitivity analysis tests (spec §11: sensitivity)."""

from __future__ import annotations

import pytest
from shapely.geometry import Point

from app.engine.contracts import Asset
from app.engine.exposure import AssetExposure
from app.engine.scoring import ScoreParams
from app.engine.sensitivity import (
    MODERATE,
    ROBUST,
    SENSITIVE,
    kendall_tau,
    sensitivity,
)


def _asset(aid: str, value: float) -> Asset:
    return Asset(aid, "school", aid, value, 0.5, "t", Point(0, 0))


def _exposures(n: int) -> list[AssetExposure]:
    return [
        AssetExposure(asset_id=f"a{i}", eta_minutes=10.0 + i * 40, confidence=0.8, reached_at=None)
        for i in range(n)
    ]


def _scenario(n: int = 12):
    assets = [_asset(f"a{i}", 95 - i * 4) for i in range(n)]
    return assets, _exposures(n)


def test_identical_parameters_overlap_one() -> None:
    assets, exps = _scenario()
    res = sensitivity(assets, exps, ScoreParams())
    baseline_run = [p for p in res.perturbations if p.parameter == "tau" and p.multiplier == 1.0]
    assert len(baseline_run) == 1
    assert baseline_run[0].top5_overlap == pytest.approx(1.0)
    assert baseline_run[0].top10_overlap == pytest.approx(1.0)
    assert baseline_run[0].kendall_tau == pytest.approx(1.0)


def test_perturbation_count_and_ranges() -> None:
    assets, exps = _scenario()
    res = sensitivity(assets, exps, ScoreParams())
    # 5 tau multipliers + 4 weights x 2 = 13 runs.
    assert len(res.perturbations) == 13
    for p in res.perturbations:
        assert 0.0 <= p.top5_overlap <= 1.0
        assert 0.0 <= p.top10_overlap <= 1.0
        assert -1.0 <= p.kendall_tau <= 1.0


def test_kendall_tau_math() -> None:
    assert kendall_tau(["a", "b", "c"], ["a", "b", "c"]) == pytest.approx(1.0)
    assert kendall_tau(["a", "b", "c"], ["c", "b", "a"]) == pytest.approx(-1.0)
    assert kendall_tau(["a", "b", "c", "d"], ["a", "c", "b", "d"]) == pytest.approx(2 / 3)


def test_rank_ranges_cover_baseline() -> None:
    assets, exps = _scenario()
    res = sensitivity(assets, exps, ScoreParams())
    assert set(res.rank_ranges) == {a.asset_id for a in assets}
    for lo, hi in res.rank_ranges.values():
        assert 1 <= lo <= hi <= len(assets)


def test_robustness_label_values() -> None:
    assets, exps = _scenario()
    res = sensitivity(assets, exps, ScoreParams())
    assert res.robustness in (ROBUST, MODERATE, SENSITIVE)
    # Clearly separated ETAs/values -> stable ranking.
    assert res.robustness == ROBUST
    assert res.most_sensitive_parameter in {
        "tau",
        "w_value",
        "w_conf",
        "w_vuln",
        "w_urgency",
    }


def test_label_logic_sensitive_case() -> None:
    # Crossed factor profiles: asset a{i} is high-value/low-vuln, b{i} the
    # reverse, with near-equal baseline risk — weight perturbations churn
    # the top-5 membership.
    assets: list[Asset] = []
    exps: list[AssetExposure] = []
    for i in range(6):
        a = Asset(f"a{i}", "school", f"a{i}", 90 - i, 0.1, "t", Point(0, 0))
        b = Asset(f"b{i}", "school", f"b{i}", 20 + i, 0.9, "t", Point(0, 0))
        assets += [a, b]
        eta = 100.0 + i * 5
        exps += [
            AssetExposure(f"a{i}", eta, 0.8, None),
            AssetExposure(f"b{i}", eta, 0.8, None),
        ]
    res = sensitivity(assets, exps, ScoreParams())
    assert res.robustness == SENSITIVE
