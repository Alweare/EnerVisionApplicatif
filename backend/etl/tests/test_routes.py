import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_get_current_reading_returns_200_with_good_quality():
    response = client.get("/api/v1/sites/SITE001/current")

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE001"
    assert body["data_quality"] == "good"
    assert body["null_reasons"] == []
    assert body["consumption_kw"] == 87.34


def test_get_current_reading_exposes_null_fields_and_reasons_when_partial():
    response = client.get("/api/v1/sites/SITE002/current")

    assert response.status_code == 200
    body = response.json()
    assert body["data_quality"] == "partial"
    assert "temperature_celsius" in body
    assert body["temperature_celsius"] is None
    assert body["null_reasons"] == ["temperature_sensor_failure"]


def test_get_current_reading_returns_reading_even_when_all_measures_are_null():
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
def test_get_current_reading_matches_site_id_for_each_mock_site(site_id):
    response = client.get(f"/api/v1/sites/{site_id}/current")

    assert response.status_code == 200
    assert response.json()["site_id"] == site_id


def test_get_current_reading_returns_404_when_site_unknown():
    response = client.get("/api/v1/sites/UNKNOWN/current")

    assert response.status_code == 404
    assert "UNKNOWN" in response.json()["detail"]


def test_get_history_returns_200_sorted_ascending_within_range():
    response = client.get(
        "/api/v1/sites/SITE001/history",
        params={"start_time": "2024-06-01T00:00:00", "end_time": "2024-06-01T05:00:00"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 6
    timestamps = [reading["timestamp"] for reading in body]
    assert timestamps == sorted(timestamps)
    assert all(reading["site_id"] == "SITE001" for reading in body)


def test_get_history_respects_limit_bounds():
    response = client.get(
        "/api/v1/sites/SITE001/history",
        params={
            "start_time": "2024-06-01T00:00:00",
            "end_time": "2024-06-01T09:00:00",
            "limit": 3,
        },
    )

    assert response.status_code == 200
    assert len(response.json()) == 3


@pytest.mark.parametrize("limit", [0, 1001, -1])
def test_get_history_returns_422_when_limit_out_of_bounds(limit):
    response = client.get("/api/v1/sites/SITE001/history", params={"limit": limit})

    assert response.status_code == 422


def test_get_history_returns_422_when_date_format_invalid():
    response = client.get(
        "/api/v1/sites/SITE001/history", params={"start_time": "not-a-date"}
    )

    assert response.status_code == 422


def test_get_history_returns_404_when_site_unknown():
    response = client.get("/api/v1/sites/UNKNOWN/history")

    assert response.status_code == 404
    assert "UNKNOWN" in response.json()["detail"]


def test_get_history_returns_422_when_start_after_end():
    response = client.get(
        "/api/v1/sites/SITE001/history",
        params={"start_time": "2024-06-01T05:00:00", "end_time": "2024-06-01T00:00:00"},
    )

    assert response.status_code == 422


def test_get_history_default_window_returns_recent_readings_without_filters():
    response = client.get("/api/v1/sites/SITE001/history")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    timestamps = [reading["timestamp"] for reading in body]
    assert timestamps == sorted(timestamps)


def test_get_sensors_status_returns_200_with_all_sites_keyed_by_id():
    response = client.get("/api/v1/sensors/status")

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"SITE001", "SITE002", "SITE003"}


def test_get_sensors_status_structure_matches_mock_api():
    response = client.get("/api/v1/sensors/status")

    site001 = response.json()["SITE001"]
    assert site001["site_name"] == "Bureau Paris La Défense"
    assert site001["overall"] == "ok"
    assert set(site001["sensors"].keys()) == {
        "consumption",
        "electrical",
        "temperature",
        "humidity",
        "network",
    }
    assert site001["sensors"]["consumption"] == {"status": "ok", "failing_until": None}


def test_get_sensors_status_exposes_degraded_and_critical_overalls():
    body = client.get("/api/v1/sensors/status").json()

    assert body["SITE002"]["overall"] == "degraded"
    assert body["SITE002"]["sensors"]["temperature"]["status"] == "failing"
    assert body["SITE003"]["overall"] == "critical"
    assert body["SITE003"]["sensors"]["network"]["status"] == "failing"
