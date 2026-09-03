import pytest
from fastapi.testclient import TestClient

from backend.workerIngestion.main import app

client = TestClient(app)


def test_get_current_reading_returns_200_with_good_quality(mock_httpx):
    response = client.get("/api/v1/sites/SITE001/current")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE001"
    assert body["data_quality"] == "good"
    assert body["null_reasons"] == []
    assert body["consumption_kw"] == 87.34


def test_get_current_reading_exposes_null_fields_and_reasons_when_partial(mock_httpx):
    response = client.get("/api/v1/sites/SITE002/current")

    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"] == "partial"
    assert "temperature_celsius" in body
    assert body["temperature_celsius"] is None
    assert body["null_reasons"] == ["temperature_sensor_failure"]


def test_get_current_reading_returns_reading_even_when_all_measures_are_null(mock_httpx):
    response = client.get("/api/v1/sites/SITE003/current")

    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"] == "critical"
    assert body["null_reasons"] == ["network_loss"]
    for field in [
        "consumption_kw",
        "consumption_kwh",
        "voltage_v",
        "current_a",
        "power_factor",
        "temperature_celsius",
        "humidity_percent",
    ]:
        assert body[field] is None


@pytest.mark.parametrize("site_id", ["SITE001", "SITE002", "SITE003"])
def test_get_current_reading_matches_site_id_for_each_mock_site(site_id, mock_httpx):
    response = client.get(f"/api/v1/sites/{site_id}/current")

    assert response.status_code == 200
    assert response.json()["site_id"] == site_id


def test_get_current_reading_returns_404_when_site_unknown(mock_httpx):
    response = client.get("/api/v1/sites/UNKNOWN/current")

    assert response.status_code == 404
    assert "UNKNOWN" in response.json()["detail"]
