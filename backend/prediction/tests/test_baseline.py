from datetime import datetime, timedelta

import pandas as pd
import pytest

from prediction.features.time_features import ROWS_PER_HOUR
from prediction.training.baseline import (
    SEASONAL_PERIOD_HOURS,
    SHORT_HORIZON_MAX_HOURS,
    attach_baseline_columns,
    baseline_mae,
    multi_horizon_baseline_mae,
    predict_baseline,
    relative_improvement,
)

START = datetime(2026, 1, 1)


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


# --- Baseline saisonnière multi-horizon -------------------------------------


def _raw_frame(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_id": "SITE_A",
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "consumption_kw": [float(i) for i in range(n)],
        }
    )


def test_short_horizon_baseline_is_persistence_of_value_at_t():
    n = SEASONAL_PERIOD_HOURS * ROWS_PER_HOUR + 100
    df = _raw_frame(n)

    out = attach_baseline_columns(df, horizons_hours=[1, SHORT_HORIZON_MAX_HOURS])

    # h <= 24h : baseline(T+h) = consumption_kw(T), quel que soit h.
    pd.testing.assert_series_equal(
        out["baseline_h1"], out["consumption_kw"], check_names=False
    )
    pd.testing.assert_series_equal(
        out[f"baseline_h{SHORT_HORIZON_MAX_HOURS}"], out["consumption_kw"], check_names=False
    )


def test_long_horizon_baseline_is_same_hour_previous_week():
    n = SEASONAL_PERIOD_HOURS * ROWS_PER_HOUR + 200
    df = _raw_frame(n)

    horizon_hours = SHORT_HORIZON_MAX_HOURS + 1  # 25h -> régime saisonnier
    out = attach_baseline_columns(df, horizons_hours=[horizon_hours])

    lag_hours = SEASONAL_PERIOD_HOURS - horizon_hours  # 143h
    expected = out["consumption_kw"].shift(lag_hours * ROWS_PER_HOUR)
    pd.testing.assert_series_equal(
        out[f"baseline_h{horizon_hours}"], expected, check_names=False
    )


def test_horizon_168_baseline_uses_value_at_t_exactly_one_week_before():
    n = SEASONAL_PERIOD_HOURS * ROWS_PER_HOUR + 50
    df = _raw_frame(n)

    out = attach_baseline_columns(df, horizons_hours=[SEASONAL_PERIOD_HOURS])

    # T + 168h - 168h = T : la référence "une semaine avant la cible" est la
    # valeur en T elle-même.
    pd.testing.assert_series_equal(
        out[f"baseline_h{SEASONAL_PERIOD_HOURS}"], out["consumption_kw"], check_names=False
    )


def test_baseline_is_computable_from_strictly_past_data_for_every_horizon():
    """
    Aucune fuite : pour chaque horizon, avec assez d'historique passé (jusqu'à
    168h derrière la dernière ligne), la baseline est calculable -- elle ne
    dépend jamais d'une valeur strictement postérieure à T.
    """
    n = SEASONAL_PERIOD_HOURS * ROWS_PER_HOUR + 10
    df = _raw_frame(n)

    out = attach_baseline_columns(df, horizons_hours=[1, 24, 25, 100, 168])

    for horizon_hours in (1, 24, 25, 100, 168):
        assert out[f"baseline_h{horizon_hours}"].iloc[-1] is not None
        assert pd.notna(out[f"baseline_h{horizon_hours}"].iloc[-1])


def test_multi_horizon_baseline_mae_is_zero_on_perfect_match():
    df = pd.DataFrame({"target_h1": [1.0, 2.0, 3.0], "baseline_h1": [1.0, 2.0, 3.0]})
    maes = multi_horizon_baseline_mae(df, horizons_hours=[1])
    assert maes[1] == pytest.approx(0.0)


def test_multi_horizon_baseline_mae_matches_manual_computation():
    df = pd.DataFrame({"target_h24": [10.0, 20.0], "baseline_h24": [12.0, 18.0]})
    maes = multi_horizon_baseline_mae(df, horizons_hours=[24])
    assert maes[24] == pytest.approx(2.0)


def test_multi_horizon_baseline_mae_drops_rows_with_missing_values():
    df = pd.DataFrame({"target_h1": [1.0, None, 3.0], "baseline_h1": [1.0, 2.0, 3.0]})
    maes = multi_horizon_baseline_mae(df, horizons_hours=[1])
    assert maes[1] == pytest.approx(0.0)
