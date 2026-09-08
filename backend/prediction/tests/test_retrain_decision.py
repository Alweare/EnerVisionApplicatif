from prediction.drift.drift_service import DriftResult
from prediction.retrain.decision import RealPerformance, should_retrain

NO_DRIFT = DriftResult(
    feature_scores={"lag_1h": 0.01},
    drifted_features=[],
    threshold=0.2,
    drift_detected=False,
)

DRIFT = DriftResult(
    feature_scores={"lag_1h": 0.9},
    drifted_features=["lag_1h"],
    threshold=0.2,
    drift_detected=True,
)


def test_no_champion_always_triggers_retrain():
    decision = should_retrain(
        has_champion=False,
        drift_result=None,
        n_new_rows=0,
        min_new_rows=1000,
    )
    assert decision.should_retrain is True
    assert "no_existing_champion" in decision.reasons


def test_no_reason_present_means_no_retrain():
    decision = should_retrain(
        has_champion=True,
        drift_result=NO_DRIFT,
        n_new_rows=10,
        min_new_rows=1000,
    )
    assert decision.should_retrain is False
    assert decision.reasons == []


def test_drift_detected_triggers_retrain():
    decision = should_retrain(
        has_champion=True,
        drift_result=DRIFT,
        n_new_rows=10,
        min_new_rows=1000,
    )
    assert decision.should_retrain is True
    assert "data_drift_detected" in decision.reasons


def test_enough_new_rows_triggers_retrain():
    decision = should_retrain(
        has_champion=True,
        drift_result=NO_DRIFT,
        n_new_rows=1500,
        min_new_rows=1000,
    )
    assert decision.should_retrain is True
    assert "enough_new_data" in decision.reasons


def test_not_enough_new_rows_does_not_trigger_retrain_alone():
    decision = should_retrain(
        has_champion=True,
        drift_result=NO_DRIFT,
        n_new_rows=999,
        min_new_rows=1000,
    )
    assert decision.should_retrain is False


def test_real_performance_degradation_triggers_retrain():
    degraded = RealPerformance(matched_rows=50, real_mae=13.0, reference_mae=10.0)
    decision = should_retrain(
        has_champion=True,
        drift_result=NO_DRIFT,
        n_new_rows=10,
        min_new_rows=1000,
        real_performance=degraded,
    )
    assert decision.should_retrain is True
    assert "real_performance_degraded" in decision.reasons


def test_real_performance_within_tolerance_does_not_trigger_retrain():
    fine = RealPerformance(matched_rows=50, real_mae=10.5, reference_mae=10.0)
    decision = should_retrain(
        has_champion=True,
        drift_result=NO_DRIFT,
        n_new_rows=10,
        min_new_rows=1000,
        real_performance=fine,
    )
    assert decision.should_retrain is False


def test_champion_unavailable_triggers_retrain():
    decision = should_retrain(
        has_champion=True,
        drift_result=NO_DRIFT,
        n_new_rows=10,
        min_new_rows=1000,
        champion_unavailable=True,
    )
    assert decision.should_retrain is True
    assert "champion_unavailable" in decision.reasons


def test_champion_unavailable_defaults_to_false():
    decision = should_retrain(
        has_champion=True,
        drift_result=NO_DRIFT,
        n_new_rows=10,
        min_new_rows=1000,
    )
    assert "champion_unavailable" not in decision.reasons


def test_missing_real_performance_is_not_a_reason_to_retrain():
    decision = should_retrain(
        has_champion=True,
        drift_result=NO_DRIFT,
        n_new_rows=10,
        min_new_rows=1000,
        real_performance=None,
    )
    assert "real_performance_degraded" not in decision.reasons


def test_multiple_reasons_are_all_reported():
    decision = should_retrain(
        has_champion=False,
        drift_result=DRIFT,
        n_new_rows=1500,
        min_new_rows=1000,
    )
    assert decision.should_retrain is True
    assert set(decision.reasons) == {
        "no_existing_champion",
        "data_drift_detected",
        "enough_new_data",
    }
