import os

import httpx

from backend.workerIngestion.schemas import EnergyReading

# URL fournie par le formateur (cf. EnerVision_Kickoff.pdf) — surchargeable
# par variable d'env pour les autres cohortes/environnements.
MOCK_API_URL = os.environ.get("MOCK_API_URL", "http://10.105.200.45:8000")

# Client partagé (pool de connexions réutilisé) plutôt qu'une connexion
# ouverte à chaque appel — ce service poll la Mock API en continu.
_client = httpx.AsyncClient(base_url=MOCK_API_URL)


async def get_current_reading(site_id: str) -> EnergyReading | None:
    response = await _client.get(f"/api/v1/sites/{site_id}/current")
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return EnergyReading(**response.json())
