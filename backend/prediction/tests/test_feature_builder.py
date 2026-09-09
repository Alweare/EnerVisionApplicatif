from datetime import datetime, timedelta

import pandas as pd
import pytest

from prediction.dataset.dataset import FEATURE_COLUMNS
from prediction.features.time_features import ROWS_PER_WEEK
from prediction.inference.feature_builder import InsufficientHistoryError, build_latest_features

START = datetime(2026, 1, 1)


def _raw_frame(n: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_id": "SITE001",
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "consumption_kw": [float(i) for i in range(n)],
            "data_quality": "good",
            "null_reason": None,
        }
    )


def test_raises_when_no_measurements_for_site(monkeypatch):
    monkeypatch.setattr(
        "prediction.inference.feature_builder.get_measurements", lambda site_id: pd.DataFrame()
    )

    with pytest.raises(InsufficientHistoryError):
        build_latest_features("SITE001")


def test_raises_when_history_too_short_for_lags(monkeypatch):
    monkeypatch.setattr(
        "prediction.inference.feature_builder.get_measurements", lambda site_id: _raw_frame(10)
    )

    with pytest.raises(InsufficientHistoryError):
        build_latest_features("SITE001")


def test_raises_when_less_than_a_week_of_history(monkeypatch):
    """
    Le forecast multi-horizon exige lag_168h/rolling_mean_168h : moins de 7
    jours d'historique (mais assez pour lag_1h/lag_24h) reste insuffisant.
    """
    monkeypatch.setattr(
        "prediction.inference.feature_builder.get_measurements",
        lambda site_id: _raw_frame(ROWS_PER_WEEK - 100),
    )

    with pytest.raises(InsufficientHistoryError):
        build_latest_features("SITE001")


def test_returns_latest_usable_row_features_and_date(monkeypatch):
    n = ROWS_PER_WEEK + 500
    raw = _raw_frame(n)
    monkeypatch.setattr(
        "prediction.inference.feature_builder.get_measurements", lambda site_id: raw
    )

    X, measurement_date = build_latest_features("SITE001")

    assert list(X.columns) == FEATURE_COLUMNS
    assert len(X) == 1
    assert not X.isna().any().any()
    assert measurement_date == raw["measurement_date"].iloc[-1]
    assert X.iloc[0]["lag_1h"] == n - 1 - 60
    assert X.iloc[0]["lag_168h"] == n - 1 - ROWS_PER_WEEK


def test_passes_site_id_through_to_repository(monkeypatch):
    captured = {}

    def fake_get_measurements(site_id):
        captured["site_id"] = site_id
        return _raw_frame(ROWS_PER_WEEK + 500)

    monkeypatch.setattr("prediction.inference.feature_builder.get_measurements", fake_get_measurements)

    build_latest_features("SITE042")

    assert captured["site_id"] == "SITE042"
