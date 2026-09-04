import os

import httpx

# URL fournie par le formateur (cf. EnerVision_Kickoff.pdf) — surchargeable
# par variable d'env pour les autres cohortes/environnements.
MOCK_API_URL = os.environ.get("MOCK_API_URL", "http://10.105.200.45:8000")

# Client partagé (pool de connexions réutilisé) plutôt qu'une connexion
# ouverte à chaque appel — ce service poll la Mock API en continu.
_client = httpx.AsyncClient(base_url=MOCK_API_URL)


async def get_current_reading_raw(site_id: str) -> httpx.Response:
    """Réponse HTTP brute, non parsée : workerIngestion n'expose rien lui-même
    et ne fait qu'archiver ce que la Mock API renvoie, sans transformation."""
    return await _client.get(f"/api/v1/sites/{site_id}/current")


async def list_site_ids() -> list[str]:
    """Découverte dynamique des sites connus (pas de liste codée en dur : le
    nombre de sites peut varier d'une cohorte/instance de Mock API à l'autre).
    """
    response = await _client.get("/api/v1/sites")
    response.raise_for_status()
    return [site["site_id"] for site in response.json()]
