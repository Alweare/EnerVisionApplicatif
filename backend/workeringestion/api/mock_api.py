import os
import httpx

# L'adresse de l'API mock dépend de l'environnement : elle est fournie par
# MOCK_API_URL (.env / docker-compose), jamais codée en dur. Le défaut ne vise
# que le développement local (mock lancé sur la machine). HTTP est assumé :
# le mock n'expose pas de TLS et n'est joignable que depuis le réseau privé.
# Une valeur vide (variable `${MOCK_API_URL}` non définie côté compose) retombe
# aussi sur le défaut.
DEFAULT_MOCK_API_URL = "http://localhost:8000"
MOCK_API_URL = os.environ.get("MOCK_API_URL") or DEFAULT_MOCK_API_URL

_client = httpx.AsyncClient(base_url=MOCK_API_URL)


async def get_current_reading_raw(site_id: str) -> httpx.Response:
    return await _client.get(f"/api/v1/sites/{site_id}/current")


async def get_alerts_raw() -> httpx.Response:
    return await _client.get("/api/v1/alerts")


async def list_site_ids() -> list[str]:
    response = await _client.get("/api/v1/sites")
    response.raise_for_status()
    return [site["site_id"] for site in response.json()]
