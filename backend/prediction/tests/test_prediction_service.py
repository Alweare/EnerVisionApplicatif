from datetime import datetime
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LinearRegression

from prediction.config import PredictionSettings
from prediction.inference.prediction_service import (
    ChampionModelCache,
    NoChampionModelError,
    PredictionService,
)
from prediction.registry import model_registry as registry

MODEL_NAME = "consumption-predictor"


def _promote_a_champion(client) -> str:
    import mlflow

    X = np.array([[1], [2], [3], [4], [5]])
    y = np.array([2, 4, 6, 8, 10])
    with mlflow.start_run():
        model = LinearRegression()
        model.fit(X, y)
        model_info = mlflow.sklearn.log_model(model, name="model")

    version = registry.register_challenger(client, MODEL_NAME, model_info.model_uri)
    registry.promote_to_champion(client, MODEL_NAME, version.version, "test")
    return str(version.version)


class FakeCache:
    def __init__(self, model, version):
        self._model = model
        self._version = version
        self.calls = 0

    def get(self, client):
        self.calls += 1
        return self._model, self._version


class FakeModel:
    def predict(self, X):
        return [42.0]


def test_champion_model_cache_raises_when_no_champion(mlflow_tracking_uri):
    client = MlflowClient()
    cache = ChampionModelCache(MODEL_NAME)

    with pytest.raises(NoChampionModelError):
        cache.get(client)


def test_champion_model_cache_raises_champion_load_error_when_artifact_unreachable(
    mlflow_tracking_uri, tmp_path
):
    import shutil

    client = MlflowClient()
    _promote_a_champion(client)
    shutil.rmtree(tmp_path / "artifacts", ignore_errors=True)

    cache = ChampionModelCache(MODEL_NAME)

    with pytest.raises(registry.ChampionLoadError):
        cache.get(client)


def test_champion_model_cache_loads_once_and_reuses(mlflow_tracking_uri, monkeypatch):
    client = MlflowClient()
    _promote_a_champion(client)

    load_calls = {"count": 0}
    original_load = registry.load_champion_model

    def counting_load(model_name):
        load_calls["count"] += 1
        return original_load(model_name)

    monkeypatch.setattr("prediction.inference.prediction_service.registry.load_champion_model", counting_load)

    cache = ChampionModelCache(MODEL_NAME)
    model_a, version_a = cache.get(client)
    model_b, version_b = cache.get(client)

    assert load_calls["count"] == 1
    assert version_a == version_b == "1"
    assert model_a is model_b


def test_champion_model_cache_reloads_on_new_champion_version(mlflow_tracking_uri):
    client = MlflowClient()
    _promote_a_champion(client)

    cache = ChampionModelCache(MODEL_NAME)
    _, first_version = cache.get(client)

    second_version = _promote_a_champion(client)
    _, reloaded_version = cache.get(client)

    assert first_version == "1"
    assert second_version == "2"
    assert reloaded_version == "2"


def test_predict_returns_expected_result(monkeypatch):
    monkeypatch.setattr(
        "prediction.inference.prediction_service.build_latest_features",
        lambda site_id: (pd.DataFrame({"lag_1h": [1.0]}), pd.Timestamp("2026-01-01T10:00:00")),
    )
    monkeypatch.setattr("prediction.inference.prediction_service.record_prediction", lambda **kwargs: None)

    settings = PredictionSettings(
        mlflow_tracking_uri="sqlite:///:memory:",
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name=MODEL_NAME,
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )
    service = PredictionService(settings=settings, cache=FakeCache(FakeModel(), "7"))

    result = service.predict("SITE001")

    assert result.site_id == "SITE001"
    assert result.predicted_consumption_kw == 42.0
    assert result.model_version == "7"
    assert result.target_timestamp == pd.Timestamp("2026-01-01T11:00:00")


def test_predict_persists_prediction_by_default(monkeypatch):
    monkeypatch.setattr(
        "prediction.inference.prediction_service.build_latest_features",
        lambda site_id: (pd.DataFrame({"lag_1h": [1.0]}), pd.Timestamp("2026-01-01T10:00:00")),
    )
    recorded = {}

    def fake_record(**kwargs):
        recorded.update(kwargs)

    monkeypatch.setattr("prediction.inference.prediction_service.record_prediction", fake_record)

    settings = PredictionSettings(
        mlflow_tracking_uri="sqlite:///:memory:",
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name=MODEL_NAME,
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )
    service = PredictionService(settings=settings, cache=FakeCache(FakeModel(), "7"))
    service.predict("SITE001")

    assert recorded["site_id"] == "SITE001"
    assert recorded["predicted_consumption_kw"] == 42.0
    assert recorded["model_version"] == "7"


def test_predict_can_skip_persistence(monkeypatch):
    monkeypatch.setattr(
        "prediction.inference.prediction_service.build_latest_features",
        lambda site_id: (pd.DataFrame({"lag_1h": [1.0]}), pd.Timestamp("2026-01-01T10:00:00")),
    )
    called = {"count": 0}
    monkeypatch.setattr(
        "prediction.inference.prediction_service.record_prediction",
        lambda **kwargs: called.__setitem__("count", called["count"] + 1),
    )

    settings = PredictionSettings(
        mlflow_tracking_uri="sqlite:///:memory:",
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name=MODEL_NAME,
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )
    service = PredictionService(settings=settings, cache=FakeCache(FakeModel(), "7"))
    service.predict("SITE001", persist=False)

    assert called["count"] == 0


def test_predict_survives_persistence_failure(monkeypatch):
    monkeypatch.setattr(
        "prediction.inference.prediction_service.build_latest_features",
        lambda site_id: (pd.DataFrame({"lag_1h": [1.0]}), pd.Timestamp("2026-01-01T10:00:00")),
    )

    def failing_record(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("prediction.inference.prediction_service.record_prediction", failing_record)

    settings = PredictionSettings(
        mlflow_tracking_uri="sqlite:///:memory:",
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name=MODEL_NAME,
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )
    service = PredictionService(settings=settings, cache=FakeCache(FakeModel(), "7"))

    result = service.predict("SITE001")

    assert result.predicted_consumption_kw == 42.0
