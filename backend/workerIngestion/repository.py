import os
from datetime import datetime

import httpx

from backend.workerIngestion.schemas import Alert, EnergyReading, Site, SiteSensorsStatus

# URL fournie par le formateur (cf. EnerVision_Kickoff.pdf) — surchargeable
# par variable d'env pour les autres cohortes/environnements.
MOCK_API_URL = os.environ.get("MOCK_API_URL", "http://10.105.200.45:8000")

# Client partagé (pool de connexions réutilisé) plutôt qu'une connexion
# ouverte à chaque appel — ce service poll la Mock API en continu.
_client = httpx.AsyncClient(base_url=MOCK_API_URL)


async def list_sites() -> list[Site]:
    response = await _client.get("/api/v1/sites")
    response.raise_for_status()
    return [Site(**item) for item in response.json()]


async def get_site(site_id: str) -> Site | None:
    response = await _client.get(f"/api/v1/sites/{site_id}")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return Site(**response.json())


async def get_current_reading(site_id: str) -> EnergyReading | None:
    response = await _client.get(f"/api/v1/sites/{site_id}/current")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return EnergyReading(**response.json())


async def get_readings(
    site_id: str | None,
    start_time: datetime | None,
    end_time: datetime | None,
    limit: int,
) -> list[EnergyReading] | None:
    params: dict[str, str | int] = {"limit": limit}
    if site_id is not None:
        params["site_id"] = site_id
    if start_time is not None:
        params["start_time"] = start_time.isoformat()
    if end_time is not None:
        params["end_time"] = end_time.isoformat()

    response = await _client.get("/api/v1/readings", params=params)
    # Un 404 n'a de sens que si on a demandé un site précis : sans site_id,
    # on ne veut pas l'avaler silencieusement et masquer une vraie erreur.
    if site_id is not None and response.status_code == 404:
        return None
    response.raise_for_status()
    return [EnergyReading(**item) for item in response.json()]


async def get_sensors_status() -> dict[str, SiteSensorsStatus]:
    response = await _client.get("/api/v1/sensors/status")
    response.raise_for_status()
    return {
        site_id: SiteSensorsStatus(**status)
        for site_id, status in response.json().items()
    }


async def list_alerts(site_id: str | None, severity: str | None) -> list[Alert]:
    params: dict[str, str] = {}
    if site_id is not None:
        params["site_id"] = site_id
    if severity is not None:
        params["severity"] = severity

    response = await _client.get("/api/v1/alerts", params=params)
    response.raise_for_status()
    return [Alert(**item) for item in response.json()]


async def get_stats_summary_raw() -> dict:
    response = await _client.get("/api/v1/stats/summary")
    response.raise_for_status()
    return response.json()


async def simulate_spike(site_id: str, duration_minutes: int) -> dict | None:
    response = await _client.post(
        f"/api/v1/simulate/spike/{site_id}",
        params={"duration_minutes": duration_minutes},
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()
