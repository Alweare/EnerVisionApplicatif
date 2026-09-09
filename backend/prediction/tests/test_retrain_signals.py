from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from prediction.retrain import signals

CLIENT = object()


def _df(n=100, start=datetime(2026, 1, 1)):
    return pd.DataFrame({"measurement_date": [start + timedelta(minutes=i) for i in range(n)]})


def test_count_new_rows_returns_full_length_when_no_champion():
    df = _df(50)
    assert signals.count_new_rows_since_champion(CLIENT, None, df) == 50


def test_count_new_rows_returns_full_length_when_champion_has_no_cutoff(monkeypatch):
    monkeypatch.setattr(
        "prediction.retrain.signals.registry.get_run_param", lambda client, run_id, key: None
    )
    champion = SimpleNamespace(run_id="run-1", version="1")
    df = _df(50)
    assert signals.count_new_rows_since_champion(CLIENT, champion, df) == 50


def test_count_new_rows_counts_rows_after_cutoff(monkeypatch):
    start = datetime(2026, 1, 1)
    cutoff = start + timedelta(minutes=30)

    monkeypatch.setattr(
        "prediction.retrain.signals.registry.get_run_param",
        lambda client, run_id, key: cutoff.isoformat(),
    )
    champion = SimpleNamespace(run_id="run-1", version="1")
    df = _df(100, start=start)

    assert signals.count_new_rows_since_champion(CLIENT, champion, df) == 69


def test_compute_real_performance_returns_none_without_champion():
    assert signals.compute_real_performance(CLIENT, None) is None


def test_compute_real_performance_returns_none_when_not_enough_matches(monkeypatch):
    champion = SimpleNamespace(run_id="run-1", version="1")
    monkeypatch.setattr(
        "prediction.retrain.signals.get_matched_predictions",
        lambda version: pd.DataFrame({"consumption_kw": [1.0] * 5, "predicted_consumption_kw": [1.0] * 5}),
    )

    assert signals.compute_real_performance(CLIENT, champion) is None


def test_compute_real_performance_returns_none_without_reference_mae(monkeypatch):
    champion = SimpleNamespace(run_id="run-1", version="1")
    n = signals.MIN_MATCHED_PREDICTIONS_FOR_REAL_PERFORMANCE
    monkeypatch.setattr(
        "prediction.retrain.signals.get_matched_predictions",
        lambda version: pd.DataFrame({"consumption_kw": [1.0] * n, "predicted_consumption_kw": [1.0] * n}),
    )
    monkeypatch.setattr(
        "prediction.retrain.signals.registry.get_run_metric", lambda client, run_id, key: None
    )

    assert signals.compute_real_performance(CLIENT, champion) is None


def test_compute_real_performance_computes_real_mae(monkeypatch):
    champion = SimpleNamespace(run_id="run-1", version="1")
    n = signals.MIN_MATCHED_PREDICTIONS_FOR_REAL_PERFORMANCE
    actual = [10.0] * n
    predicted = [12.0] * n

    monkeypatch.setattr(
        "prediction.retrain.signals.get_matched_predictions",
        lambda version: pd.DataFrame({"consumption_kw": actual, "predicted_consumption_kw": predicted}),
    )
    monkeypatch.setattr(
        "prediction.retrain.signals.registry.get_run_metric", lambda client, run_id, key: 1.5
    )

    result = signals.compute_real_performance(CLIENT, champion)

    assert result.matched_rows == n
    assert result.real_mae == pytest.approx(2.0)
    assert result.reference_mae == pytest.approx(1.5)
