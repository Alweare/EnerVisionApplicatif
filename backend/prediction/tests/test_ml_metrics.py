from datetime import datetime, timedelta

import pandas as pd
import pytest

from prediction.config import PredictionSettings
from prediction.observability import ml_metrics
from prediction.training.pipeline import run_training_pipeline

START = datetime(2026, 1, 1)
MODEL_NAME = "consumption-predictor"


N_ROWS = 25_000  # cf. test_training_pipeline.py : historique nécessaire au multi-horizon


def _linear_raw_frame(n: int = N_ROWS) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_id": "SITE_A",
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "consumption_kw": [float(i) for i in range(n)],
            "data_quality": "good",
            "null_reason": None,
        }
    )


def _settings(tracking_uri: str) -> PredictionSettings:
    return PredictionSettings(
        mlflow_tracking_uri=tracking_uri,
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name=MODEL_NAME,
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )


def _counter_value(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


def test_observe_prediction_success_increments_metrics():
    before = _counter_value(ml_metrics.PREDICTION_REQUESTS_TOTAL, result="success")

    ml_metrics.observe_prediction_success(0.05)

    assert _counter_value(ml_metrics.PREDICTION_REQUESTS_TOTAL, result="success") == before + 1


def test_observe_prediction_error_increments_metrics_with_reason():
    before_requests = _counter_value(ml_metrics.PREDICTION_REQUESTS_TOTAL, result="error")
    before_errors = _counter_value(ml_metrics.PREDICTION_ERRORS_TOTAL, reason="no_champion_model")

    ml_metrics.observe_prediction_error("no_champion_model", 0.02)

    assert _counter_value(ml_metrics.PREDICTION_REQUESTS_TOTAL, result="error") == before_requests + 1
    assert (
        _counter_value(ml_metrics.PREDICTION_ERRORS_TOTAL, reason="no_champion_model")
        == before_errors + 1
    )


def test_refresh_ml_metrics_handles_missing_experiment_gracefully(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri)
    ml_metrics.refresh_ml_metrics(settings=settings)


def test_refresh_ml_metrics_swallows_unexpected_errors(monkeypatch):
    monkeypatch.setattr(
        "prediction.observability.ml_metrics.mlflow.set_tracking_uri",
        lambda uri: (_ for _ in ()).throw(RuntimeError("mlflow unreachable")),
    )

    ml_metrics.refresh_ml_metrics(settings=_settings("sqlite:///:memory:"))


def test_refresh_ml_metrics_reflects_champion_and_training_state(monkeypatch, mlflow_tracking_uri):
    monkeypatch.setattr(
        "prediction.dataset.dataset.get_measurements", lambda: _linear_raw_frame().copy()
    )
    settings = _settings(mlflow_tracking_uri)

    result = run_training_pipeline(settings=settings)
    assert result.promoted is True

    ml_metrics.refresh_ml_metrics(settings=settings)

    assert ml_metrics.ML_LAST_TRAINING_MAE._value.get() == pytest.approx(result.mae)
    assert ml_metrics.ML_BASELINE_MAE._value.get() == pytest.approx(result.baseline_mae)
    assert ml_metrics.ML_CHAMPION_MAE._value.get() == pytest.approx(result.mae)
    assert ml_metrics.ML_MODEL_PROMOTIONS_TOTAL._value.get() == 1
    assert (
        ml_metrics.ML_CURRENT_MODEL_INFO.labels(
            model_name=MODEL_NAME, alias="champion", version=result.model_version
        )._value.get()
        == 1
    )

    # Horizons clés (§14 du besoin) : la dégradation de la MAE avec l'horizon
    # doit être visible dans Prometheus, pas seulement dans MLflow.
    assert ml_metrics.ML_MAE_H24._value.get() == pytest.approx(result.mae_h24)
    assert ml_metrics.ML_MAE_H48._value.get() == pytest.approx(result.mae_h48)
    assert ml_metrics.ML_BASELINE_MAE_H24._value.get() == pytest.approx(result.baseline_mae_h24)
    assert ml_metrics.ML_BASELINE_MAE_H48._value.get() == pytest.approx(result.baseline_mae_h48)


def test_observe_forecast_success_increments_metrics_and_points_counter():
    before_requests = _counter_value(ml_metrics.FORECAST_REQUESTS_TOTAL, result="success")
    before_points = ml_metrics.FORECAST_POINTS_GENERATED_TOTAL._value.get()

    ml_metrics.observe_forecast_success(0.2, n_points=24)

    assert _counter_value(ml_metrics.FORECAST_REQUESTS_TOTAL, result="success") == before_requests + 1
    assert ml_metrics.FORECAST_POINTS_GENERATED_TOTAL._value.get() == before_points + 24


def test_observe_forecast_error_increments_metrics_with_reason():
    before_requests = _counter_value(ml_metrics.FORECAST_REQUESTS_TOTAL, result="error")
    before_errors = _counter_value(ml_metrics.FORECAST_ERRORS_TOTAL, reason="no_champion_model")

    ml_metrics.observe_forecast_error("no_champion_model", 0.02)

    assert _counter_value(ml_metrics.FORECAST_REQUESTS_TOTAL, result="error") == before_requests + 1
    assert (
        _counter_value(ml_metrics.FORECAST_ERRORS_TOTAL, reason="no_champion_model") == before_errors + 1
    )
