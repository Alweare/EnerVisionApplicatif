from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LinearRegression

from prediction.config import PredictionSettings
from prediction.dataset.dataset import MAX_HORIZON_HOURS
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
    """
    Simule un régresseur multi-output : une ligne, MAX_HORIZON_HOURS colonnes
    (predictions[0][h-1] = valeur prédite pour l'horizon h). La valeur pour
    h=1 (index 0) reste 42.0 pour ne pas changer les assertions historiques de
    ce fichier ; les valeurs augmentent ensuite avec l'horizon, ce qui permet
    de vérifier l'ordre/l'indexation des points de forecast.
    """

    def predict(self, X):
        return np.array([[42.0 + horizon_index for horizon_index in range(MAX_HORIZON_HOURS)]])


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


# --- Forecast multi-horizon --------------------------------------------------


def _settings() -> PredictionSettings:
    return PredictionSettings(
        mlflow_tracking_uri="sqlite:///:memory:",
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name=MODEL_NAME,
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )


BASE_TIMESTAMP = pd.Timestamp("2026-01-01T10:00:00")


def _service_with_fake_champion(monkeypatch, base_timestamp=BASE_TIMESTAMP, recorded=None):
    monkeypatch.setattr(
        "prediction.inference.prediction_service.build_latest_features",
        lambda site_id: (pd.DataFrame({"lag_1h": [1.0]}), base_timestamp),
    )
    if recorded is None:
        recorded = []
    monkeypatch.setattr(
        "prediction.inference.prediction_service.record_predictions",
        lambda rows: recorded.extend(rows),
    )
    return PredictionService(settings=_settings(), cache=FakeCache(FakeModel(), "7")), recorded


@pytest.mark.parametrize("hours", [1, 24, 48])
def test_forecast_returns_exactly_hours_points(monkeypatch, hours):
    service, _ = _service_with_fake_champion(monkeypatch)

    result = service.forecast("SITE001", hours=hours)

    assert len(result.points) == hours
    assert result.horizon_hours == hours


def test_forecast_points_are_chronologically_ordered(monkeypatch):
    service, _ = _service_with_fake_champion(monkeypatch)

    result = service.forecast("SITE001", hours=24)

    horizons = [point.horizon_hours for point in result.points]
    timestamps = [point.target_timestamp for point in result.points]
    assert horizons == list(range(1, 25))
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == 24


def test_forecast_target_timestamp_is_base_timestamp_plus_horizon(monkeypatch):
    service, _ = _service_with_fake_champion(monkeypatch, base_timestamp=BASE_TIMESTAMP)

    result = service.forecast("SITE001", hours=3)

    assert result.base_timestamp == BASE_TIMESTAMP
    assert result.points[0].target_timestamp == BASE_TIMESTAMP + timedelta(hours=1)
    assert result.points[1].target_timestamp == BASE_TIMESTAMP + timedelta(hours=2)
    assert result.points[2].target_timestamp == BASE_TIMESTAMP + timedelta(hours=3)


def test_forecast_predicted_values_match_model_output_per_horizon(monkeypatch):
    service, _ = _service_with_fake_champion(monkeypatch)

    result = service.forecast("SITE001", hours=5)

    # FakeModel : valeur pour l'horizon h = 42.0 + (h - 1).
    assert [point.predicted_consumption_kw for point in result.points] == [42.0, 43.0, 44.0, 45.0, 46.0]


def test_forecast_uses_a_future_dated_base_timestamp_not_the_system_clock(monkeypatch):
    """
    §5 du besoin : le dataset peut contenir des mesures postérieures à
    l'horloge système (données simulées/historiques). `target_timestamp` doit
    toujours être calculé depuis `base_timestamp` (issu des données), jamais
    depuis l'horloge système -- même quand `base_timestamp` est "dans le futur"
    par rapport à `generated_at`.
    """
    far_future_base = pd.Timestamp("2099-06-15T12:22:09")
    service, _ = _service_with_fake_champion(monkeypatch, base_timestamp=far_future_base)

    result = service.forecast("SITE001", hours=2)

    assert result.base_timestamp == far_future_base
    assert result.points[0].target_timestamp == far_future_base + timedelta(hours=1)
    assert result.points[1].target_timestamp == far_future_base + timedelta(hours=2)
    # generated_at reflète l'horloge système réelle, pas la donnée simulée.
    real_now = pd.Timestamp.now(tz="UTC")
    assert abs((result.generated_at - real_now).total_seconds()) < 5
    assert result.generated_at != result.base_timestamp


def test_forecast_persists_every_point_in_one_batch(monkeypatch):
    service, recorded = _service_with_fake_champion(monkeypatch)

    result = service.forecast("SITE001", hours=24)

    assert len(recorded) == 24
    assert {row["horizon_hours"] for row in recorded} == set(range(1, 25))
    assert all(row["site_id"] == "SITE001" for row in recorded)
    assert all(row["model_version"] == "7" for row in recorded)
    first = next(row for row in recorded if row["horizon_hours"] == 1)
    assert first["predicted_for"] == result.points[0].target_timestamp
    assert first["predicted_consumption_kw"] == result.points[0].predicted_consumption_kw


def test_forecast_can_skip_persistence(monkeypatch):
    service, recorded = _service_with_fake_champion(monkeypatch)

    service.forecast("SITE001", hours=24, persist=False)

    assert recorded == []


def test_forecast_survives_persistence_failure(monkeypatch):
    monkeypatch.setattr(
        "prediction.inference.prediction_service.build_latest_features",
        lambda site_id: (pd.DataFrame({"lag_1h": [1.0]}), BASE_TIMESTAMP),
    )

    def failing_record(rows):
        raise RuntimeError("db down")

    monkeypatch.setattr("prediction.inference.prediction_service.record_predictions", failing_record)
    service = PredictionService(settings=_settings(), cache=FakeCache(FakeModel(), "7"))

    result = service.forecast("SITE001", hours=24)

    assert len(result.points) == 24


@pytest.mark.parametrize("hours", [0, -1, 169, 1000])
def test_forecast_rejects_hours_outside_valid_range(monkeypatch, hours):
    service, _ = _service_with_fake_champion(monkeypatch)

    with pytest.raises(ValueError):
        service.forecast("SITE001", hours=hours)


def test_forecast_calls_feature_builder_exactly_once_not_recursively(monkeypatch):
    """
    Approche directe multi-output, jamais récursive : une seule construction
    de features / un seul appel `model.predict`, quel que soit `hours`.
    """
    calls = {"count": 0}

    def counting_build_latest_features(site_id):
        calls["count"] += 1
        return pd.DataFrame({"lag_1h": [1.0]}), BASE_TIMESTAMP

    monkeypatch.setattr(
        "prediction.inference.prediction_service.build_latest_features", counting_build_latest_features
    )
    monkeypatch.setattr("prediction.inference.prediction_service.record_predictions", lambda rows: None)
    service = PredictionService(settings=_settings(), cache=FakeCache(FakeModel(), "7"))

    service.forecast("SITE001", hours=48)

    assert calls["count"] == 1
