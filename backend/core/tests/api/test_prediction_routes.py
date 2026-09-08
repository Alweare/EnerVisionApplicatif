from datetime import datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from core.api.schemas import PredictionRead
from core.api.service.prediction_service import (
    ModelNotAvailableError,
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


def _prediction(site_id: str = "SITE001") -> PredictionRead:
    return PredictionRead(
        site_id=site_id,
        predicted_consumption_kw=187.3,
        prediction_date=datetime(2026, 9, 8, 13, 0, 0),
        model_name="consumption-predictor",
        model_version="3",
        generated_at=datetime(2026, 9, 8, 12, 0, 0),
    )


# --- GET /api/v1/backend/prediction/{site_id} ---------------------------

def test_get_site_prediction_returns_200_with_prediction(prediction_service):
    prediction_service.get_prediction.return_value = _prediction("SITE001")

    response = client.get("/api/v1/backend/prediction/SITE001")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE001"
    assert body["predicted_consumption_kw"] == 187.3
    assert body["model_name"] == "consumption-predictor"
    prediction_service.get_prediction.assert_called_once_with("SITE001")


def test_get_site_prediction_returns_404_when_site_unknown(prediction_service):
    prediction_service.get_prediction.side_effect = SiteNotFoundError("SITE999")

    response = client.get("/api/v1/backend/prediction/SITE999")

    assert response.status_code == 404
    assert "SITE999" in response.json()["detail"]


def test_get_site_prediction_returns_503_when_no_model_available(prediction_service):
    prediction_service.get_prediction.side_effect = ModelNotAvailableError()

    response = client.get("/api/v1/backend/prediction/SITE001")

    assert response.status_code == 503
    assert response.json()["detail"]
