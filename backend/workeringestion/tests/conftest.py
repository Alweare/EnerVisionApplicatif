import httpx
import pytest

from workeringestion import repository

# Jeux de données figés, calqués sur la forme réelle de la Mock API
# (vérifiée en direct sur http://10.105.200.45:8000) mais avec des valeurs
# fixes pour des assertions déterministes en tests.

CURRENT_READINGS_JSON = {
    "SITE001": {
        "timestamp": "2024-06-15T14:32:00.123456",
        "site_id": "SITE001",
        "site_type": "office",
        "consumption_kw": 87.34,
        "consumption_kwh": 87.34,
        "voltage_v": 401.2,
        "current_a": 132.5,
        "power_factor": 0.923,
        "temperature_celsius": 22.1,
        "humidity_percent": 58.4,
        "null_reasons": [],
        "data_quality": "good",
    },
    "SITE002": {
        "timestamp": "2024-06-15T14:32:05.987654",
        "site_id": "SITE002",
        "site_type": "factory",
        "consumption_kw": 542.10,
        "consumption_kwh": 542.10,
        "voltage_v": 398.5,
        "current_a": 826.4,
        "power_factor": 0.921,
        "temperature_celsius": None,
        "humidity_percent": 61.8,
        "null_reasons": ["temperature_sensor_failure"],
        "data_quality": "partial",
    },
    "SITE003": {
        "timestamp": "2024-06-15T14:32:10.111111",
        "site_id": "SITE003",
        "site_type": "datacenter",
        "consumption_kw": None,
        "consumption_kwh": None,
        "voltage_v": None,
        "current_a": None,
        "power_factor": None,
        "temperature_celsius": None,
        "humidity_percent": None,
        "null_reasons": ["network_loss"],
        "data_quality": "critical",
    },
}


def fake_response(status_code: int, json_data=None) -> httpx.Response:
    request = httpx.Request("GET", "http://mock-api.test")
    return httpx.Response(status_code, json=json_data, request=request)


@pytest.fixture
def mock_httpx(monkeypatch):
    """Route le client httpx partagé du repository vers les fixtures ci-dessus, sans réseau."""

    async def fake_get(url: str, params: dict | None = None) -> httpx.Response:
        if url.endswith("/current"):
            site_id = url.rsplit("/", 2)[-2]
            reading = CURRENT_READINGS_JSON.get(site_id)
            if reading is None:
                return fake_response(404, {"detail": f"Site {site_id} non trouvé"})
            return fake_response(200, reading)

        raise AssertionError(f"URL non mockée dans ce tests : {url}")

    monkeypatch.setattr(repository._client, "get", fake_get)
