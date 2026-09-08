from datetime import datetime, timedelta

import pandas as pd
import pytest
from mlflow.tracking import MlflowClient

from prediction.config import PredictionSettings
from prediction.registry.model_registry import get_model_version_by_alias
from prediction.training.pipeline import run_training_pipeline

START = datetime(2026, 1, 1)
MODEL_NAME = "consumption-predictor"


def _linear_raw_frame(n: int = 3000) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_id": "SITE_A",
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "consumption_kw": [float(i) for i in range(n)],
            "data_quality": "good",
            "null_reason": None,
        }
    )


@pytest.fixture(autouse=True)
def _patch_measurements(monkeypatch):
    raw = _linear_raw_frame()
    monkeypatch.setattr("prediction.dataset.dataset.get_measurements", lambda: raw.copy())


def _settings(**overrides) -> PredictionSettings:
    base = dict(
        mlflow_tracking_uri="",
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name=MODEL_NAME,
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )
    base.update(overrides)
    return PredictionSettings(**base)


def test_first_candidate_becomes_champion_when_it_beats_baseline(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)

    result = run_training_pipeline(settings=settings)

    assert result.promoted is True
    assert result.champion_mae is None
    assert result.mae < result.baseline_mae

    client = MlflowClient()
    champion = client.get_model_version_by_alias(MODEL_NAME, "champion")
    assert str(champion.version) == result.model_version


def test_candidate_rejected_when_it_does_not_beat_baseline(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_baseline=1.5)

    result = run_training_pipeline(settings=settings)

    assert result.promoted is False
    assert "baseline" in result.reason

    client = MlflowClient()
    assert get_model_version_by_alias(client, MODEL_NAME, "champion") is None
    rejected_version = client.get_model_version(MODEL_NAME, result.model_version)
    assert rejected_version.tags.get("rejected") == "true"


def test_better_challenger_replaces_champion(mlflow_tracking_uri):
    first_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=first_settings)
    assert first.promoted is True

    lenient_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_champion=-1.0)
    second = run_training_pipeline(settings=lenient_settings)

    assert second.promoted is True
    assert second.champion_mae is not None

    client = MlflowClient()
    champion = client.get_model_version_by_alias(MODEL_NAME, "champion")
    assert str(champion.version) == second.model_version
    assert str(champion.version) != first.model_version


def test_worse_challenger_is_rejected_and_champion_is_unchanged(mlflow_tracking_uri):
    first_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=first_settings)
    assert first.promoted is True

    strict_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_champion=0.9)
    second = run_training_pipeline(settings=strict_settings)

    assert second.promoted is False
    assert "champion" in second.reason

    client = MlflowClient()
    champion = client.get_model_version_by_alias(MODEL_NAME, "champion")
    assert str(champion.version) == first.model_version

    rejected = client.get_model_version(MODEL_NAME, second.model_version)
    assert rejected.tags.get("rejected") == "true"


def test_history_of_all_versions_is_preserved(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=settings)

    lenient_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_champion=-1.0)
    second = run_training_pipeline(settings=lenient_settings)

    client = MlflowClient()
    all_versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    versions = {str(v.version) for v in all_versions}

    assert first.model_version in versions
    assert second.model_version in versions
    assert client.get_model_version(MODEL_NAME, first.model_version) is not None


def test_drift_is_none_on_first_run_and_computed_on_second_run(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=settings)
    assert first.drift_result is None

    second = run_training_pipeline(settings=settings)
    assert second.drift_result is not None
    assert set(second.drift_result.feature_scores.keys()) <= {"lag_1h", "lag_24h", "rolling_mean_24h"}


def test_logged_run_has_expected_params_and_metrics(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    result = run_training_pipeline(settings=settings, trigger_source="cli_train_if_needed", retrain_reasons=["no_existing_champion"])

    client = MlflowClient()
    run = client.get_run(result.run_id)

    assert "n_validation_rows" in run.data.params
    assert "n_test_rows" in run.data.params
    assert "dataset_max_date" in run.data.params
    assert run.data.metrics["mae"] == pytest.approx(result.mae)
    assert run.data.metrics["baseline_mae"] == pytest.approx(result.baseline_mae)
    assert run.data.tags["trigger_source"] == "cli_train_if_needed"
    assert run.data.tags["retrain_reasons"] == "no_existing_champion"
