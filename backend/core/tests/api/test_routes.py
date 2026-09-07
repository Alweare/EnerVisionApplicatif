from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from core.api.schemas import MeasurementRead, SiteRead
from core.api.service.measurement_service import (
    MeasurementNotFoundError,
    SiteNotFoundError,
)
from shared.database import get_db
from core.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _override_get_db():
    """Neutralise la vraie session DB : les services sont mockés dans chaque tests."""
    app.dependency_overrides[get_db] = lambda: None
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def site_service(monkeypatch):
    fake = Mock()
    monkeypatch.setattr("core.api.controller.site.SiteService", lambda db: fake)
    return fake


@pytest.fixture
def measurement_service(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(
        "core.api.controller.measurement.MeasurementService", lambda db: fake
    )
    return fake


def _site(site_id: str = "SITE001") -> SiteRead:
    return SiteRead(
        site_id=site_id,
        site_type="office",
        site_name="Bureau Paris",
        location="Paris, France",
        capacity_kw=200.0,
        status="active",
    )


def _measurement(site_id: str = "SITE001", date: datetime | None = None) -> MeasurementRead:
    return MeasurementRead(
        measurement_id=uuid4(),
        site_id=site_id,
        measurement_date=date or datetime(2026, 9, 4, 9, 0, 0),
        consumption_kw=104.47,
        consumption_kwh=104.47,
        voltage_v=402.6,
        current_a=163.9,
        power_factor=0.914,
        temperature_celsius=None,
        humidity_percent=61.0,
        null_reason=["temperature_sensor_failure"],
        data_quality="partial",
        created_at=datetime(2026, 9, 4, 9, 9, 1),
    )


# --- GET /api/v1/backend/sites --------------------------------------------

def test_list_sites_returns_200_with_all_sites(site_service):
    site_service.list_sites.return_value = [_site("SITE001"), _site("SITE002")]

    response = client.get("/api/v1/backend/sites")

    assert response.status_code == 200
    body = response.json()
    assert [s["site_id"] for s in body] == ["SITE001", "SITE002"]
    assert body[0]["capacity_kw"] == 200.0


def test_list_sites_returns_empty_list(site_service):
    site_service.list_sites.return_value = []

    response = client.get("/api/v1/backend/sites")

    assert response.status_code == 200
    assert response.json() == []


# --- GET /api/v1/backend/sites/{site_id} --------------------------------

def test_get_site_returns_200_with_site(site_service):
    site_service.get_site.return_value = _site("SITE001")

    response = client.get("/api/v1/backend/sites/SITE001")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE001"
    assert body["site_name"] == "Bureau Paris"
    site_service.get_site.assert_called_once_with("SITE001")


def test_get_site_returns_404_when_site_unknown(site_service):
    site_service.get_site.side_effect = SiteNotFoundError("SITE999")

    response = client.get("/api/v1/backend/sites/SITE999")

    assert response.status_code == 404
    assert "SITE999" in response.json()["detail"]


# --- GET /api/v1/backend/sites/{site_id}/measurements --------------------

def test_list_site_measurements_returns_200_with_rows(measurement_service):
    measurement_service.list_measurements.return_value = [_measurement(), _measurement()]

    response = client.get("/api/v1/backend/sites/SITE001/measurements")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["site_id"] == "SITE001"
    assert body[0]["null_reason"] == ["temperature_sensor_failure"]


def test_list_site_measurements_uses_default_pagination(measurement_service):
    measurement_service.list_measurements.return_value = []

    client.get("/api/v1/backend/sites/SITE001/measurements")

    measurement_service.list_measurements.assert_called_once_with(
        "SITE001", limit=100, offset=0
    )


def test_list_site_measurements_forwards_pagination_params(measurement_service):
    measurement_service.list_measurements.return_value = []

    client.get("/api/v1/backend/sites/SITE001/measurements?limit=5&offset=20")

    measurement_service.list_measurements.assert_called_once_with(
        "SITE001", limit=5, offset=20
    )


def test_list_site_measurements_returns_404_when_site_unknown(measurement_service):
    measurement_service.list_measurements.side_effect = SiteNotFoundError("SITE999")

    response = client.get("/api/v1/backend/sites/SITE999/measurements")

    assert response.status_code == 404
    assert "SITE999" in response.json()["detail"]


@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "offset=-1", "limit=abc"])
def test_list_site_measurements_rejects_invalid_pagination(measurement_service, query):
    measurement_service.list_measurements.return_value = []

    response = client.get(f"/api/v1/backend/sites/SITE001/measurements?{query}")

    assert response.status_code == 422


# --- GET /api/v1/backend/sites/{site_id}/current (régression) -----------

def test_get_site_current_measurement_returns_200(measurement_service):
    measurement_service.get_current_measurement.return_value = _measurement()

    response = client.get("/api/v1/backend/sites/SITE001/current")

    assert response.status_code == 200
    assert response.json()["site_id"] == "SITE001"


@pytest.mark.parametrize(
    "error",
    [SiteNotFoundError("SITE001"), MeasurementNotFoundError("SITE001")],
)
def test_get_site_current_measurement_maps_known_errors_to_404(
    measurement_service, error
):
    measurement_service.get_current_measurement.side_effect = error

    response = client.get("/api/v1/backend/sites/SITE001/current")

    assert response.status_code == 404
