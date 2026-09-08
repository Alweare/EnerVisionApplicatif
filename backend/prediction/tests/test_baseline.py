import pandas as pd
import pytest

from prediction.training.baseline import (
    baseline_mae,
    predict_baseline,
    relative_improvement,
)


def test_predict_baseline_returns_lag_1h_column():
    X = pd.DataFrame({"lag_1h": [1.0, 2.0, 3.0], "lag_24h": [9.0, 9.0, 9.0]})
    predictions = predict_baseline(X)
    assert list(predictions) == [1.0, 2.0, 3.0]


def test_baseline_mae_is_zero_when_lag_1h_perfectly_predicts_target():
    X = pd.DataFrame({"lag_1h": [1.0, 2.0, 3.0]})
    y = pd.Series([1.0, 2.0, 3.0])
    assert baseline_mae(X, y) == pytest.approx(0.0)


def test_baseline_mae_matches_manual_computation():
    X = pd.DataFrame({"lag_1h": [1.0, 2.0, 3.0]})
    y = pd.Series([2.0, 2.0, 6.0])
    # |1-2| + |2-2| + |3-6| = 1 + 0 + 3 = 4 -> mean = 4/3
    assert baseline_mae(X, y) == pytest.approx(4 / 3)


def test_relative_improvement_positive_when_candidate_beats_reference():
    assert relative_improvement(reference_mae=10.0, candidate_mae=8.0) == pytest.approx(0.2)


def test_relative_improvement_negative_when_candidate_worse_than_reference():
    assert relative_improvement(reference_mae=10.0, candidate_mae=12.0) == pytest.approx(-0.2)


def test_relative_improvement_zero_when_equal():
    assert relative_improvement(reference_mae=10.0, candidate_mae=10.0) == pytest.approx(0.0)


def test_relative_improvement_handles_zero_reference_mae():
    assert relative_improvement(reference_mae=0.0, candidate_mae=0.0) == pytest.approx(0.0)
    assert relative_improvement(reference_mae=0.0, candidate_mae=1.0) == float("-inf")
