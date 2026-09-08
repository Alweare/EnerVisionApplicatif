from datetime import datetime, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from prediction.api.app import app
from prediction.api.controller.prediction import get_prediction_service
from prediction.inference.feature_builder import InsufficientHistoryError
from prediction.inference.prediction_service import NoChampionModelError, PredictionResult


class FakeService:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error

    def predict(self, site_id: str):
        if self._error is not None:
            raise self._error
        return self._result


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
