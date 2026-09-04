import os

import httpx

# URL du formateur (EnerVision_Kickoff.pdf) — surchargeable par env pour les
# autres cohortes/environnements.
MOCK_API_URL = os.environ.get("MOCK_API_URL", "http://10.105.200.45:8000")

# Client partagé : le polling tourne en continu, pas de connexion à la volée.
_client = httpx.AsyncClient(base_url=MOCK_API_URL)


async def get_current_reading_raw(site_id: str) -> httpx.Response:
    """Réponse HTTP brute, non parsée — aucune transformation ici."""
    return await _client.get(f"/api/v1/sites/{site_id}/current")


async def list_site_ids() -> list[str]:
    """Sites découverts dynamiquement (le nombre varie selon l'instance de Mock API)."""
    response = await _client.get("/api/v1/sites")
    response.raise_for_status()
    return [site["site_id"] for site in response.json()]
