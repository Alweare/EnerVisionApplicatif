from __future__ import annotations

from dataclasses import dataclass

from prediction.drift.drift_service import DriftResult

REAL_PERFORMANCE_DEGRADATION_FACTOR = 1.2


@dataclass(frozen=True)
class RealPerformance:
    matched_rows: int
    real_mae: float
    reference_mae: float


@dataclass(frozen=True)
class RetrainDecision:
    should_retrain: bool
    reasons: list[str]


def should_retrain(
    has_champion: bool,
    drift_result: DriftResult | None,
    n_new_rows: int,
    min_new_rows: int,
    real_performance: RealPerformance | None = None,
) -> RetrainDecision:
    reasons: list[str] = []

    if not has_champion:
        reasons.append("no_existing_champion")

    if drift_result is not None and drift_result.drift_detected:
        reasons.append("data_drift_detected")

    if n_new_rows >= min_new_rows:
        reasons.append("enough_new_data")

    if (
        real_performance is not None
        and real_performance.reference_mae > 0
        and real_performance.real_mae > real_performance.reference_mae * REAL_PERFORMANCE_DEGRADATION_FACTOR
    ):
        reasons.append("real_performance_degraded")

    return RetrainDecision(should_retrain=bool(reasons), reasons=reasons)
