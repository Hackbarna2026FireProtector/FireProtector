"""Ranking sensitivity analysis (spec §7.3).

One-at-a-time perturbations around the baseline parameters:
``tau`` at {0.5, 0.75, 1.0, 1.5, 2.0}x plus each weight at +/-50%.
(Recorded in DECISIONS.md — the spec left joint-vs-marginal open.)

Per perturbation: re-rank, then report top-5/top-10 overlap with the
baseline ranking and Kendall's tau. Ranks are unique (deterministic
tie-break), so Kendall's tau reduces to an inversion count.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.engine.contracts import Asset
from app.engine.exposure import AssetExposure
from app.engine.scoring import ScoreParams, score_assets

_TAU_MULTIPLIERS = (0.5, 0.75, 1.0, 1.5, 2.0)
_WEIGHT_MULTIPLIERS = (0.5, 1.5)
_WEIGHT_FIELDS = ("w_value", "w_conf", "w_vuln", "w_urgency")

ROBUST = "robust"
MODERATE = "moderate"
SENSITIVE = "sensitive"


@dataclass(frozen=True)
class Perturbation:
    """One parameter perturbation and its agreement with the baseline."""

    parameter: str
    multiplier: float
    top5_overlap: float
    top10_overlap: float
    kendall_tau: float


@dataclass(frozen=True)
class SensitivityResult:
    """Full sensitivity report for a parameter set."""

    perturbations: list[Perturbation]
    rank_ranges: dict[str, list[int]] = field(default_factory=dict)
    robustness: str = ROBUST
    most_sensitive_parameter: str = ""


def _inversions(order: list[int]) -> int:
    """Count inversions in ``order`` via merge sort (O(n log n))."""

    def sort_count(items: list[int]) -> tuple[list[int], int]:
        n = len(items)
        if n < 2:
            return items, 0
        mid = n // 2
        left, inv_l = sort_count(items[:mid])
        right, inv_r = sort_count(items[mid:])
        merged: list[int] = []
        i = j = 0
        inv = inv_l + inv_r
        while i < len(left) and j < len(right):
            if left[i] <= right[j]:
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1
                inv += len(left) - i
        merged.extend(left[i:])
        merged.extend(right[j:])
        return merged, inv

    return sort_count(order)[1]


def kendall_tau(baseline_order: list[str], perturbed_order: list[str]) -> float:
    """Kendall's tau between two strict rankings of the same items."""
    n = len(baseline_order)
    if n < 2:
        return 1.0
    base_rank = {asset_id: i for i, asset_id in enumerate(baseline_order)}
    perm = [base_rank[a] for a in perturbed_order]
    total = n * (n - 1) // 2
    discordant = _inversions(perm)
    return (total - 2 * discordant) / total


def _top_k_overlap(base: list[str], other: list[str], k: int) -> float:
    if not base:
        return 1.0
    kk = min(k, len(base))
    return len(set(base[:kk]) & set(other[:kk])) / kk


def _clamped(params: ScoreParams, field_name: str, multiplier: float) -> ScoreParams:
    """Copy params with one field multiplied, clamped to its valid range."""
    bounds = {
        "tau": (15.0, 360.0),
        "w_value": (0.0, 3.0),
        "w_conf": (0.0, 3.0),
        "w_vuln": (0.0, 3.0),
        "w_urgency": (0.0, 3.0),
    }[field_name]
    value = getattr(params, field_name) * multiplier
    value = min(max(value, bounds[0]), bounds[1])
    return params.model_copy(update={field_name: value})


def ranking_of(result_assets: list) -> list[str]:
    """Ordered asset_ids by rank for a scored result."""
    return [a.asset_id for a in sorted(result_assets, key=lambda a: a.rank)]


def sensitivity(
    assets: list[Asset],
    exposures: list[AssetExposure],
    params: ScoreParams,
) -> SensitivityResult:
    """Perturb each parameter one at a time and measure ranking stability."""
    cases: list[tuple[str, float, ScoreParams]] = [
        ("tau", m, _clamped(params, "tau", m)) for m in _TAU_MULTIPLIERS
    ]
    for field_name in _WEIGHT_FIELDS:
        for m in _WEIGHT_MULTIPLIERS:
            cases.append((field_name, m, _clamped(params, field_name, m)))

    baseline = ranking_of(score_assets(assets, exposures, params).assets)
    perturbations: list[Perturbation] = []
    rank_seen: dict[str, list[int]] = {}
    for i, asset_id in enumerate(baseline):
        rank_seen[asset_id] = [i + 1, i + 1]

    for field_name, m, perturbed_params in cases:
        order = ranking_of(score_assets(assets, exposures, perturbed_params).assets)
        perturbations.append(
            Perturbation(
                parameter=field_name,
                multiplier=m,
                top5_overlap=_top_k_overlap(baseline, order, 5),
                top10_overlap=_top_k_overlap(baseline, order, 10),
                kendall_tau=kendall_tau(baseline, order),
            )
        )
        for i, asset_id in enumerate(order):
            rng = rank_seen[asset_id]
            rng[0] = min(rng[0], i + 1)
            rng[1] = max(rng[1], i + 1)

    non_baseline = [p for p in perturbations if not (p.parameter == "tau" and p.multiplier == 1.0)]
    min_top5 = min((p.top5_overlap for p in non_baseline), default=1.0)
    robustness = ROBUST if min_top5 >= 0.8 else MODERATE if min_top5 >= 0.6 else SENSITIVE

    by_param: dict[str, list[float]] = {}
    for p in non_baseline:
        by_param.setdefault(p.parameter, []).append(p.top5_overlap)
    most_sensitive = min(by_param, key=lambda p: sum(by_param[p]) / len(by_param[p]), default="")

    return SensitivityResult(
        perturbations=perturbations,
        rank_ranges=rank_seen,
        robustness=robustness,
        most_sensitive_parameter=most_sensitive,
    )
