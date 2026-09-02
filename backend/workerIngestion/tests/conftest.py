import httpx
import pytest

from backend.workerIngestion import repository

# Jeux de données figés, calqués sur la forme réelle de la Mock API
# (vérifiée en direct sur http://10.105.200.45:8000) mais avec des valeurs
# fixes pour des assertions déterministes en test.

SITES_JSON = [
    {
        "site_id": "SITE001",
        "site_type": "office",
        "site_name": "Bureau Paris La Défense",
        "location": "Paris, France",
        "capacity_kw": 200.0,
        "status": "active",
    },
    {
        "site_id": "SITE002",
        "site_type": "factory",
        "site_name": "Usine Lyon Vénissieux",
        "location": "Lyon, France",
        "capacity_kw": 1000.0,
        "status": "active",
    },
    {
        "site_id": "SITE003",
        "site_type": "datacenter",
        "site_name": "Data Center Marseille",
        "location": "Marseille, France",
        "capacity_kw": 800.0,
        "status": "active",
    },
]

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

SENSORS_STATUS_JSON = {
    "SITE001": {
        "site_name": "Bureau Paris La Défense",
        "sensors": {
            "consumption": {"status": "ok", "failing_until": None},
            "electrical": {"status": "ok", "failing_until": None},
            "temperature": {"status": "ok", "failing_until": None},
            "humidity": {"status": "ok", "failing_until": None},
            "network": {"status": "ok", "failing_until": None},
        },
        "overall": "ok",
    },
    "SITE003": {
        "site_name": "Data Center Marseille",
        "sensors": {
            "consumption": {"status": "ok", "failing_until": None},
            "electrical": {"status": "ok", "failing_until": None},
            "temperature": {"status": "ok", "failing_until": None},
            "humidity": {"status": "ok", "failing_until": None},
            "network": {
                "status": "failing",
                "failing_until": "2024-06-15T14:40:00",
            },
        },
        "overall": "critical",
    },
}

ALERTS_JSON = [
    {
        "alert_id": "ALR-SITE001-1718458200",
        "timestamp": "2024-06-15T14:10:00",
        "site_id": "SITE001",
        "severity": "low",
        "type": "threshold",
        "message": "Consommation légèrement au-dessus du seuil",
        "value": 95.0,
        "threshold": 90.0,
    },
    {
        "alert_id": "ALR-SITE002-1718458320",
        "timestamp": "2024-06-15T14:12:00",
        "site_id": "SITE002",
        "severity": "critical",
        "type": "outage",
        "message": "Risque de surcharge sur Usine Lyon Vénissieux",
        "value": 812.5,
        "threshold": 720.0,
    },
]

STATS_SUMMARY_JSON = {
    "timestamp": "2024-06-15T14:32:00",
    "total_sites": 3,
    "total_consumption_kw": 629.44,
    "total_capacity_kw": 2000,
    "average_load_percent": 31.5,
    "sites": [
        {
            "site_id": "SITE001",
            "site_name": "Bureau Paris La Défense",
            "current_consumption_kw": 87.34,
            "capacity_kw": 200,
            "load_percent": 43.7,
            "data_quality": "good",
        },
        {
            "site_id": "SITE002",
            "site_name": "Usine Lyon Vénissieux",
            "current_consumption_kw": 542.10,
            "capacity_kw": 1000,
            "load_percent": 54.2,
            "data_quality": "partial",
        },
        {
            "site_id": "SITE003",
            "site_name": "Data Center Marseille",
            "current_consumption_kw": None,
            "capacity_kw": 800,
            "load_percent": None,
            "data_quality": "critical",
        },
    ],
}


def fake_response(status_code: int, json_data=None) -> httpx.Response:
    request = httpx.Request("GET", "http://mock-api.test")
    return httpx.Response(status_code, json=json_data, request=request)


@pytest.fixture
def mock_httpx(monkeypatch):
    """Route le client httpx partagé du repository vers les fixtures ci-dessus, sans réseau."""

    async def fake_get(url: str, params: dict | None = None) -> httpx.Response:
        params = params or {}

        if url.endswith("/api/v1/sites"):
            return fake_response(200, SITES_JSON)

        if url.endswith("/api/v1/readings"):
            site_id = params.get("site_id")
            if site_id == "UNKNOWN":
                return fake_response(404, {"detail": "Site UNKNOWN non trouvé"})
            reading = CURRENT_READINGS_JSON.get(site_id, CURRENT_READINGS_JSON["SITE001"])
            return fake_response(200, [reading])

        if url.endswith("/current"):
            site_id = url.rsplit("/", 2)[-2]
            reading = CURRENT_READINGS_JSON.get(site_id)
            if reading is None:
                return fake_response(404, {"detail": f"Site {site_id} non trouvé"})
            return fake_response(200, reading)

        if "/api/v1/sites/" in url:
            site_id = url.rsplit("/", 1)[-1]
            site = next((s for s in SITES_JSON if s["site_id"] == site_id), None)
            if site is None:
                return fake_response(404, {"detail": f"Site {site_id} non trouvé"})
            return fake_response(200, site)

        if url.endswith("/api/v1/sensors/status"):
            return fake_response(200, SENSORS_STATUS_JSON)

        if url.endswith("/api/v1/alerts"):
            alerts = ALERTS_JSON
            if params.get("site_id"):
                alerts = [a for a in alerts if a["site_id"] == params["site_id"]]
            if params.get("severity"):
                alerts = [a for a in alerts if a["severity"] == params["severity"]]
            return fake_response(200, alerts)

        if url.endswith("/api/v1/stats/summary"):
            return fake_response(200, STATS_SUMMARY_JSON)

        raise AssertionError(f"URL non mockée dans ce test : {url}")

    async def fake_post(url: str, params: dict | None = None) -> httpx.Response:
        params = params or {}
        if "/api/v1/simulate/spike/" in url:
            site_id = url.rsplit("/", 1)[-1]
            if site_id == "UNKNOWN":
                return fake_response(404, {"detail": "Site UNKNOWN non trouvé"})
            return fake_response(
                200,
                {
                    "status": "simulated",
                    "site_id": site_id,
                    "event": "consumption_spike",
                    "duration_minutes": params.get("duration_minutes", 30),
                    "message": f"Pic de consommation simulé sur {site_id}.",
                },
            )
        raise AssertionError(f"URL non mockée dans ce test : {url}")

    monkeypatch.setattr(repository._client, "get", fake_get)
    monkeypatch.setattr(repository._client, "post", fake_post)
