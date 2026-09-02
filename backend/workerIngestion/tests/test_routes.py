from fastapi.testclient import TestClient

from backend.workerIngestion.main import app

client = TestClient(app)


def test_get_sites_returns_200_with_all_sites(mock_httpx):
    response = client.get("/api/v1/sites")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    assert body[0]["capacity_kw"] == 200.0


def test_get_site_by_id_returns_200_with_matching_site(mock_httpx):
    response = client.get("/api/v1/sites/SITE002")

    assert response.status_code == 200
    assert response.json()["site_id"] == "SITE002"


def test_get_site_by_id_returns_404_when_unknown(mock_httpx):
    response = client.get("/api/v1/sites/UNKNOWN")

    assert response.status_code == 404


def test_get_current_reading_returns_200(mock_httpx):
    response = client.get("/api/v1/sites/SITE001/current")

    assert response.status_code == 200
    assert response.json()["data_quality"] == "good"


def test_get_current_reading_returns_404_when_unknown(mock_httpx):
    response = client.get("/api/v1/sites/UNKNOWN/current")

    assert response.status_code == 404


def test_get_readings_returns_200_filtered_by_site_id(mock_httpx):
    response = client.get("/api/v1/readings", params={"site_id": "SITE002"})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["site_id"] == "SITE002"


def test_get_readings_returns_404_when_site_unknown(mock_httpx):
    response = client.get("/api/v1/readings", params={"site_id": "UNKNOWN"})

    assert response.status_code == 404


def test_get_readings_returns_422_when_limit_out_of_bounds(mock_httpx):
    response = client.get("/api/v1/readings", params={"limit": 99999})

    assert response.status_code == 422


def test_get_readings_returns_422_when_date_format_invalid(mock_httpx):
    response = client.get("/api/v1/readings", params={"start_time": "not-a-date"})

    assert response.status_code == 422


def test_get_sensors_status_returns_200(mock_httpx):
    response = client.get("/api/v1/sensors/status")

    assert response.status_code == 200
    assert response.json()["SITE003"]["overall"] == "critical"


def test_get_alerts_returns_200_with_all_alerts(mock_httpx):
    response = client.get("/api/v1/alerts")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_get_alerts_returns_200_empty_list_for_unknown_severity(mock_httpx):
    # Aligné sur le comportement réel de la Mock API : pas de 422 ici, une
    # sévérité non reconnue ne filtre simplement rien en (liste vide).
    response = client.get("/api/v1/alerts", params={"severity": "not-a-severity"})

    assert response.status_code == 200
    assert response.json() == []


def test_get_stats_summary_returns_200_with_has_incomplete_data(mock_httpx):
    response = client.get("/api/v1/stats/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["has_incomplete_data"] is True
    assert body["total_consumption_kw"] == 629.44


def test_simulate_spike_returns_200_for_known_site(mock_httpx):
    response = client.post(
        "/api/v1/simulate/spike/SITE002", params={"duration_minutes": 60}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["site_id"] == "SITE002"
    assert body["duration_minutes"] == 60


def test_simulate_spike_returns_404_for_unknown_site(mock_httpx):
    response = client.post("/api/v1/simulate/spike/UNKNOWN")

    assert response.status_code == 404


def test_simulate_spike_returns_422_when_duration_out_of_bounds(mock_httpx):
    response = client.post(
        "/api/v1/simulate/spike/SITE002", params={"duration_minutes": 999}
    )

    assert response.status_code == 422
