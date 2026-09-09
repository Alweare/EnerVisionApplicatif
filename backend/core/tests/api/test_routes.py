from datetime import datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from core.api.schemas import (
    AlertRead,
    MeasurementRead,
    SiteRead,
    SiteWithCurrentRead,
)
from core.api.service.measurement_service import (
    MeasurementNotFoundError,
    SiteNotFoundError,
)
from core.security import AuthenticatedUser, get_current_user
from shared.database import get_db
from core.main import app

client = TestClient(app)

_TEST_USER_ID = "7e57c0de-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def _override_get_db():
    """Neutralise la vraie session DB : les services sont mockés dans chaque tests."""
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        sub=_TEST_USER_ID, username="test"
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def site_service(monkeypatch):
    fake = Mock()
    monkeypatch.setattr("core.api.controller.site.SiteService", lambda db: fake)
    return fake


@pytest.fixture
def alert_service(monkeypatch):
    fake = Mock()
    monkeypatch.setattr("core.api.controller.alert.AlertService", lambda db: fake)
    return fake


@pytest.fixture
def measurement_service(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(
        "core.api.controller.measurement.MeasurementService", lambda db: fake
    )
    return fake


@pytest.fixture
def me_service(monkeypatch):
    fake = Mock()
    monkeypatch.setattr("core.api.controller.me.SiteService", lambda db: fake)
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


def _site_with_current(
    site_id: str = "SITE001",
    current_consumption_kw: float | None = 104.47,
    data_quality: str | None = "good",
) -> SiteWithCurrentRead:
    return SiteWithCurrentRead(
        **_site(site_id).model_dump(),
        current_consumption_kw=current_consumption_kw,
        data_quality=data_quality,
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


# --- GET /api/v1/sites ---------------------------------------------------

def test_list_sites_returns_200_with_all_sites(site_service):
    site_service.list_sites.return_value = [_site("SITE001"), _site("SITE002")]

    response = client.get("/api/v1/sites")

    assert response.status_code == 200
    body = response.json()
    assert [s["site_id"] for s in body] == ["SITE001", "SITE002"]
    assert body[0]["capacity_kw"] == 200.0


def test_list_sites_returns_empty_list(site_service):
    site_service.list_sites.return_value = []

    response = client.get("/api/v1/sites")

    assert response.status_code == 200
    assert response.json() == []


# --- GET /api/v1/sites/{site_id} ---------------------------------------

def test_get_site_returns_200_with_site(site_service):
    site_service.get_site.return_value = _site("SITE001")

    response = client.get("/api/v1/sites/SITE001")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE001"
    assert body["site_name"] == "Bureau Paris"
    site_service.get_site.assert_called_once_with("SITE001")


def test_get_site_returns_404_when_site_unknown(site_service):
    site_service.get_site.side_effect = SiteNotFoundError("SITE999")

    response = client.get("/api/v1/sites/SITE999")

    assert response.status_code == 404
    assert "SITE999" in response.json()["detail"]


# --- GET /api/v1/me/sites ----------------------------------------------

def test_list_my_sites_returns_sites_with_current_consumption(me_service):
    me_service.list_sites_for_user.return_value = [
        _site_with_current("SITE001", current_consumption_kw=104.47, data_quality="good"),
        _site_with_current("SITE003", current_consumption_kw=None, data_quality=None),
    ]

    response = client.get("/api/v1/me/sites")

    assert response.status_code == 200
    body = response.json()
    assert [s["site_id"] for s in body] == ["SITE001", "SITE003"]
    assert body[0]["current_consumption_kw"] == 104.47
    assert body[0]["data_quality"] == "good"
    assert body[1]["current_consumption_kw"] is None
    me_service.list_sites_for_user.assert_called_once_with(
        UUID(_TEST_USER_ID), True
    )


def test_list_my_sites_forwards_active_only_false(me_service):
    me_service.list_sites_for_user.return_value = []

    response = client.get("/api/v1/me/sites?active_only=false")

    assert response.status_code == 200
    me_service.list_sites_for_user.assert_called_once_with(UUID(_TEST_USER_ID), False)


def test_list_my_sites_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)

    response = client.get("/api/v1/me/sites")

    assert response.status_code == 401


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


# --- GET /api/v1/backend/alerts ------------------------------------------

def _alert(site_id: str = "SITE001", alert_id: str = "ALR-SITE001-1") -> AlertRead:
    return AlertRead(
        alert_id=alert_id,
        site_id=site_id,
        severity="critical",
        type="spike",
        message="Pic de consommation détecté",
        value=812.5,
        threshold=720.0,
        created_at=datetime(2026, 9, 7, 15, 18, 29),
    )


def test_list_alerts_returns_200_with_rows(alert_service):
    alert_service.list_alerts.return_value = [
        _alert("SITE001"), _alert("SITE002", "ALR-SITE002-1")
    ]

    response = client.get("/api/v1/backend/alerts")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["alert_id"] == "ALR-SITE001-1"
    assert body[1]["site_id"] == "SITE002"


def test_list_alerts_uses_default_pagination_and_no_site_filter(alert_service):
    alert_service.list_alerts.return_value = []

    client.get("/api/v1/backend/alerts")

    alert_service.list_alerts.assert_called_once_with(
        site_id=None, since=None, severities=None, limit=100, offset=0
    )


def test_list_alerts_forwards_the_site_filter(alert_service):
    alert_service.list_alerts.return_value = []

    client.get("/api/v1/backend/alerts?site_id=SITE002")

    alert_service.list_alerts.assert_called_once_with(
        site_id="SITE002", since=None, severities=None, limit=100, offset=0
    )


def test_list_alerts_forwards_pagination_params(alert_service):
    alert_service.list_alerts.return_value = []

    client.get("/api/v1/backend/alerts?limit=5&offset=20")

    alert_service.list_alerts.assert_called_once_with(
        site_id=None, since=None, severities=None, limit=5, offset=20
    )


def test_list_alerts_returns_404_when_site_unknown(alert_service):
    alert_service.list_alerts.side_effect = SiteNotFoundError("SITE999")

    response = client.get("/api/v1/backend/alerts?site_id=SITE999")

    assert response.status_code == 404
    assert "SITE999" in response.json()["detail"]


@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "offset=-1", "limit=abc"])
def test_list_alerts_rejects_invalid_pagination(alert_service, query):
    alert_service.list_alerts.return_value = []

    response = client.get(f"/api/v1/backend/alerts?{query}")

    assert response.status_code == 422


def test_list_alerts_forwards_the_since_bound(alert_service):
    alert_service.list_alerts.return_value = []

    client.get("/api/v1/backend/alerts?since=2026-08-09T00:00:00")

    alert_service.list_alerts.assert_called_once_with(
        site_id=None, since=datetime(2026, 8, 9, 0, 0), severities=None,
        limit=100, offset=0
    )


def test_list_alerts_rejects_an_unparsable_since(alert_service):
    alert_service.list_alerts.return_value = []

    assert client.get("/api/v1/backend/alerts?since=pas-une-date").status_code == 422


def test_list_alerts_forwards_a_single_severity(alert_service):
    alert_service.list_alerts.return_value = []

    client.get("/api/v1/backend/alerts?severity=critical")

    alert_service.list_alerts.assert_called_once_with(
        site_id=None, since=None, severities=["critical"], limit=100, offset=0
    )


def test_list_alerts_forwards_several_severities(alert_service):
    alert_service.list_alerts.return_value = []

    client.get("/api/v1/backend/alerts?severity=high&severity=critical")

    alert_service.list_alerts.assert_called_once_with(
        site_id=None,
        since=None,
        severities=["high", "critical"],
        limit=100,
        offset=0,
    )


def test_list_alerts_combines_site_and_severity_filters(alert_service):
    alert_service.list_alerts.return_value = []

    client.get("/api/v1/backend/alerts?site_id=SITE002&severity=low")

    alert_service.list_alerts.assert_called_once_with(
        site_id="SITE002", since=None, severities=["low"], limit=100, offset=0
    )
