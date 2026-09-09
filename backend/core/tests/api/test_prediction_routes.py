from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from core.api.schemas import (
    HistoryPoint,
    PredictionPoint,
    PredictionRead,
    SitePredictionRead,
)
from core.api.service.prediction_service import (
    PredictionNotAvailableError,
    SiteNotFoundError,
)
from shared.database import get_db
from core.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _override_get_db():
    """Neutralise la vraie session DB : le service est mocké dans chaque test."""
    app.dependency_overrides[get_db] = lambda: None
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def prediction_service(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(
        "core.api.controller.prediction.PredictionService", lambda db: fake
    )
    return fake


def _history_point(hour: int = 9, consumption_kw: float = 104.47) -> HistoryPoint:
    return HistoryPoint(
        measured_at=datetime(2026, 9, 8, hour, 0, 0),
        consumption_kw=consumption_kw,
    )


def _site_prediction(site_id: str = "SITE001") -> SitePredictionRead:
    return SitePredictionRead(
        site_id=site_id,
        prediction=PredictionRead(
            prediction_id=uuid4(),
            site_id=site_id,
            predicted_for=datetime(2026, 9, 8, 18, 0, 0),
            predicted_consumption_kw=145.0,
            model_version="v0.1.0-seed",
            created_at=datetime(2026, 9, 8, 11, 0, 0),
        ),
        points=[
            PredictionPoint(
                predicted_for=datetime(2026, 9, 8, 14, 0, 0),
                predicted_consumption_kw=120.0,
            ),
            PredictionPoint(
                predicted_for=datetime(2026, 9, 8, 18, 0, 0),
                predicted_consumption_kw=145.0,
            ),
        ],
        history=[_history_point(8), _history_point(9)],
    )


# --- GET /api/v1/backend/sites/{site_id}/predictions ------------------

def test_get_site_predictions_returns_200_with_bundle(prediction_service):
    prediction_service.get_prediction.return_value = _site_prediction("SITE001")

    response = client.get("/api/v1/backend/sites/SITE001/predictions")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE001"
    assert body["prediction"]["predicted_consumption_kw"] == 145.0
    assert body["prediction"]["predicted_for"] == "2026-09-08T18:00:00"
    assert [p["predicted_consumption_kw"] for p in body["points"]] == [120.0, 145.0]
    assert body["prediction"]["model_version"] == "v0.1.0-seed"
    assert [h["measured_at"] for h in body["history"]] == [
        "2026-09-08T08:00:00",
        "2026-09-08T09:00:00",
    ]
    prediction_service.get_prediction.assert_called_once_with(
        "SITE001", history_hours=24
    )


def test_get_site_predictions_forwards_history_hours(prediction_service):
    prediction_service.get_prediction.return_value = _site_prediction()

    client.get("/api/v1/backend/sites/SITE001/predictions?history_hours=48")

    prediction_service.get_prediction.assert_called_once_with(
        "SITE001", history_hours=48
    )


@pytest.mark.parametrize(
    "query", ["history_hours=0", "history_hours=169", "history_hours=abc"]
)
def test_get_site_predictions_rejects_invalid_history_hours(prediction_service, query):
    prediction_service.get_prediction.return_value = _site_prediction()

    response = client.get(f"/api/v1/backend/sites/SITE001/predictions?{query}")

    assert response.status_code == 422


def test_get_site_predictions_returns_404_when_site_unknown(prediction_service):
    prediction_service.get_prediction.side_effect = SiteNotFoundError("SITE999")

    response = client.get("/api/v1/backend/sites/SITE999/predictions")

    assert response.status_code == 404
    assert "SITE999" in response.json()["detail"]


def test_get_site_predictions_returns_503_when_no_prediction(prediction_service):
    prediction_service.get_prediction.side_effect = PredictionNotAvailableError("SITE001")

    response = client.get("/api/v1/backend/sites/SITE001/predictions")

    assert response.status_code == 503
    assert "SITE001" in response.json()["detail"]
