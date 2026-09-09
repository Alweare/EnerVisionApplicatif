from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from prediction.api.app import app
from prediction.api.controller.prediction import get_prediction_service
from prediction.inference.feature_builder import InsufficientHistoryError
from prediction.inference.prediction_service import (
    ForecastPointResult,
    ForecastResult,
    NoChampionModelError,
    PredictionResult,
)
from prediction.registry.model_registry import ChampionLoadError


class FakeService:
    def __init__(self, result=None, forecast_result=None, error=None):
        self._result = result
        self._forecast_result = forecast_result
        self._error = error

    def predict(self, site_id: str):
        if self._error is not None:
            raise self._error
        return self._result

    def forecast(self, site_id: str, hours: int):
        if self._error is not None:
            raise self._error
        return self._forecast_result


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_prediction_returns_200_with_expected_payload(client):
    result = PredictionResult(
        site_id="SITE001",
        prediction_timestamp=pd.Timestamp("2026-01-01T12:00:00", tz=timezone.utc),
        target_timestamp=pd.Timestamp("2026-01-01T13:00:00", tz=timezone.utc),
        predicted_consumption_kw=42.5,
        model_version="3",
    )
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(result=result)

    response = client.get("/api/v1/sites/SITE001/prediction")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE001"
    assert body["predicted_consumption_kw"] == 42.5
    assert body["model_version"] == "3"


def test_get_prediction_returns_404_when_insufficient_history(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        error=InsufficientHistoryError("SITE001")
    )

    response = client.get("/api/v1/sites/SITE001/prediction")

    assert response.status_code == 404


def test_get_prediction_returns_503_when_no_champion(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        error=NoChampionModelError("consumption-predictor")
    )

    response = client.get("/api/v1/sites/SITE001/prediction")

    assert response.status_code == 503


def test_get_prediction_returns_503_when_champion_artifact_is_unreachable(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        error=ChampionLoadError("consumption-predictor", RuntimeError("No such artifact: ''"))
    )

    response = client.get("/api/v1/sites/SITE001/prediction")

    assert response.status_code == 503


def test_get_prediction_returns_500_on_unexpected_error(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        error=RuntimeError("boom")
    )

    response = client.get("/api/v1/sites/SITE001/prediction")

    assert response.status_code == 500


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint_is_exposed(client, monkeypatch):
    monkeypatch.setattr("prediction.api.app.refresh_ml_metrics", lambda: None)

    response = client.get("/metrics")

    assert response.status_code == 200
    assert b"prediction_requests_total" in response.content


# --- /forecast ----------------------------------------------------------


BASE_TIMESTAMP = datetime(2026, 1, 1, 12, 0, 0)
GENERATED_AT = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)


def _forecast_result(hours: int) -> ForecastResult:
    return ForecastResult(
        site_id="SITE001",
        generated_at=GENERATED_AT,
        base_timestamp=BASE_TIMESTAMP,
        horizon_hours=hours,
        model_version="7",
        points=[
            ForecastPointResult(
                horizon_hours=h,
                target_timestamp=BASE_TIMESTAMP + timedelta(hours=h),
                predicted_consumption_kw=6.0 + h * 0.1,
            )
            for h in range(1, hours + 1)
        ],
    )


@pytest.mark.parametrize("hours", [1, 24, 168])
def test_get_forecast_returns_200_with_exactly_hours_points(client, hours):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        forecast_result=_forecast_result(hours)
    )

    response = client.get(f"/api/v1/sites/SITE001/forecast?hours={hours}")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE001"
    assert body["horizon_hours"] == hours
    assert len(body["predictions"]) == hours


def test_get_forecast_points_are_in_chronological_order(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        forecast_result=_forecast_result(24)
    )

    response = client.get("/api/v1/sites/SITE001/forecast?hours=24")

    body = response.json()
    horizons = [point["horizon_hours"] for point in body["predictions"]]
    timestamps = [point["target_timestamp"] for point in body["predictions"]]
    assert horizons == list(range(1, 25))
    assert timestamps == sorted(timestamps)


def test_get_forecast_target_timestamp_matches_base_timestamp_plus_horizon(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        forecast_result=_forecast_result(3)
    )

    response = client.get("/api/v1/sites/SITE001/forecast?hours=3")

    body = response.json()
    assert body["base_timestamp"] == BASE_TIMESTAMP.isoformat()
    first_point = body["predictions"][0]
    assert first_point["target_timestamp"] == (BASE_TIMESTAMP + timedelta(hours=1)).isoformat()


def test_get_forecast_default_hours_is_24(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        forecast_result=_forecast_result(24)
    )

    response = client.get("/api/v1/sites/SITE001/forecast")

    assert response.status_code == 200
    assert len(response.json()["predictions"]) == 24


def test_get_forecast_rejects_hours_zero(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        forecast_result=_forecast_result(1)
    )

    response = client.get("/api/v1/sites/SITE001/forecast?hours=0")

    assert response.status_code == 422


def test_get_forecast_rejects_hours_above_168(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        forecast_result=_forecast_result(168)
    )

    response = client.get("/api/v1/sites/SITE001/forecast?hours=169")

    assert response.status_code == 422


def test_get_forecast_returns_404_when_insufficient_history(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        error=InsufficientHistoryError("SITE001")
    )

    response = client.get("/api/v1/sites/SITE001/forecast?hours=24")

    assert response.status_code == 404


def test_get_forecast_returns_503_when_no_champion(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        error=NoChampionModelError("consumption-predictor")
    )

    response = client.get("/api/v1/sites/SITE001/forecast?hours=24")

    assert response.status_code == 503


def test_get_forecast_returns_503_when_champion_artifact_is_unreachable(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(
        error=ChampionLoadError("consumption-predictor", RuntimeError("No such artifact: ''"))
    )

    response = client.get("/api/v1/sites/SITE001/forecast?hours=24")

    assert response.status_code == 503


def test_get_forecast_returns_500_on_unexpected_error(client):
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(error=RuntimeError("boom"))

    response = client.get("/api/v1/sites/SITE001/forecast?hours=24")

    assert response.status_code == 500


def test_old_prediction_endpoint_still_works_unchanged(client):
    """Compatibilité : /prediction reste T+1h, inchangé par l'ajout de /forecast."""
    result = PredictionResult(
        site_id="SITE001",
        prediction_timestamp=pd.Timestamp("2026-01-01T12:00:00", tz=timezone.utc),
        target_timestamp=pd.Timestamp("2026-01-01T13:00:00", tz=timezone.utc),
        predicted_consumption_kw=42.5,
        model_version="3",
    )
    app.dependency_overrides[get_prediction_service] = lambda: FakeService(result=result)

    response = client.get("/api/v1/sites/SITE001/prediction")

    assert response.status_code == 200
    body = response.json()
    assert body["predicted_consumption_kw"] == 42.5
    assert "predictions" not in body
