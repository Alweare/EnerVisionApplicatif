from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from prediction.config import PredictionSettings
from prediction.drift.drift_service import DriftResult
from prediction.retrain.orchestrator import train_if_needed

START = datetime(2026, 1, 1)

NO_DRIFT = DriftResult(feature_scores={"lag_1h": 0.01}, drifted_features=[], threshold=0.2, drift_detected=False)
DRIFT = DriftResult(feature_scores={"lag_1h": 0.9}, drifted_features=["lag_1h"], threshold=0.2, drift_detected=True)


# Le modèle multi-horizon exige lag_168h (historique) et target_h48 (futur
# connu jusqu'à T+48h) pour qu'une ligne soit exploitable, mais un signal
# hebdomadaire n'est réellement APPRENABLE par XGBoost que sur plusieurs
# semaines de train (cf. test_training_pipeline.py pour le raisonnement complet).
N_ROWS = 10_000
MINUTES_PER_ROW = 10  # aligné sur ROWS_PER_HOUR=6 (échantillonnage 10 min)


def _seasonal_raw_frame(n: int = N_ROWS, start: datetime = START, seed: int = 0) -> pd.DataFrame:
    """Consommation bornée, saisonnalité journalière/hebdomadaire + bruit --
    cf. test_training_pipeline.py::_seasonal_raw_frame pour le raisonnement
    (XGBoost n'extrapole pas une rampe non bornée)."""
    rng = np.random.default_rng(seed)
    minutes = np.arange(n)
    hours = (minutes * MINUTES_PER_ROW / 60.0) % 24
    day_of_week = (minutes * MINUTES_PER_ROW // (60 * 24)) % 7
    is_weekend = (day_of_week >= 5).astype(float)

    daily_pattern = 10 + 6 * np.sin((hours - 7) / 24 * 2 * np.pi) + 3 * np.sin((hours - 18) / 12 * 2 * np.pi)
    consumption = np.clip(daily_pattern - 2.0 * is_weekend + rng.normal(0, 0.5, size=n), 0.5, None)

    return pd.DataFrame(
        {
            "site_id": "SITE_A",
            "measurement_date": [start + timedelta(minutes=MINUTES_PER_ROW * i) for i in range(n)],
            "consumption_kw": consumption,
            "data_quality": "good",
            "null_reason": None,
        }
    )


def _patch_measurements(monkeypatch, raw: pd.DataFrame) -> None:
    monkeypatch.setattr("prediction.dataset.dataset.get_measurements", lambda: raw.copy())


def _patch_no_ground_truth(monkeypatch) -> None:
    monkeypatch.setattr(
        "prediction.retrain.signals.get_matched_predictions",
        lambda version: pd.DataFrame(columns=["consumption_kw", "predicted_consumption_kw"]),
    )


def _patch_drift(monkeypatch, result: DriftResult) -> None:
    monkeypatch.setattr("prediction.retrain.orchestrator.detect_drift", lambda reference, df, threshold: result)


def _settings(tracking_uri: str, **overrides) -> PredictionSettings:
    base = dict(
        mlflow_tracking_uri=tracking_uri,
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name="consumption-predictor",
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )
    base.update(overrides)
    return PredictionSettings(**base)


def test_trains_when_no_champion_exists(mlflow_tracking_uri, monkeypatch):
    _patch_measurements(monkeypatch, _seasonal_raw_frame())
    _patch_no_ground_truth(monkeypatch)
    settings = _settings(mlflow_tracking_uri)

    decision, result = train_if_needed(settings=settings)

    assert decision.should_retrain is True
    assert "no_existing_champion" in decision.reasons
    assert result is not None
    assert result.promoted is True


def test_skips_when_nothing_changed_since_champion(mlflow_tracking_uri, monkeypatch):
    raw = _seasonal_raw_frame()
    _patch_measurements(monkeypatch, raw)
    _patch_no_ground_truth(monkeypatch)
    settings = _settings(mlflow_tracking_uri, min_new_rows=1_000_000)

    first_decision, first_result = train_if_needed(settings=settings)
    assert first_result is not None

    _patch_drift(monkeypatch, NO_DRIFT)
    second_decision, second_result = train_if_needed(settings=settings)

    assert second_decision.should_retrain is False
    assert second_decision.reasons == []
    assert second_result is None


def test_retrains_when_enough_new_rows_accumulated(mlflow_tracking_uri, monkeypatch):
    _patch_measurements(monkeypatch, _seasonal_raw_frame(n=N_ROWS))
    _patch_no_ground_truth(monkeypatch)
    settings = _settings(mlflow_tracking_uri, min_new_rows=100)

    first_decision, first_result = train_if_needed(settings=settings)
    assert first_result is not None

    _patch_measurements(monkeypatch, _seasonal_raw_frame(n=N_ROWS + 2000))
    _patch_drift(monkeypatch, NO_DRIFT)
    second_decision, second_result = train_if_needed(settings=settings)

    assert second_decision.should_retrain is True
    assert "enough_new_data" in second_decision.reasons
    assert second_result is not None


def test_retrains_when_drift_detected(mlflow_tracking_uri, monkeypatch):
    _patch_measurements(monkeypatch, _seasonal_raw_frame())
    _patch_no_ground_truth(monkeypatch)
    settings = _settings(mlflow_tracking_uri, min_new_rows=1_000_000)

    first_decision, first_result = train_if_needed(settings=settings)
    assert first_result is not None

    _patch_drift(monkeypatch, DRIFT)
    second_decision, second_result = train_if_needed(settings=settings)

    assert second_decision.should_retrain is True
    assert "data_drift_detected" in second_decision.reasons
    assert second_result is not None


def test_retrains_and_recovers_when_champion_artifact_is_unreachable(mlflow_tracking_uri, monkeypatch, tmp_path):
    import shutil

    _patch_measurements(monkeypatch, _seasonal_raw_frame())
    _patch_no_ground_truth(monkeypatch)
    settings = _settings(mlflow_tracking_uri, min_new_rows=1_000_000)

    first_decision, first_result = train_if_needed(settings=settings)
    assert first_result is not None
    assert first_result.promoted is True

    shutil.rmtree(tmp_path / "artifacts", ignore_errors=True)
    _patch_drift(monkeypatch, NO_DRIFT)

    second_decision, second_result = train_if_needed(settings=settings)

    assert second_decision.should_retrain is True
    assert "champion_unavailable" in second_decision.reasons
    assert second_result is not None
    assert second_result.promoted is True
    assert second_result.champion_unavailable is True
