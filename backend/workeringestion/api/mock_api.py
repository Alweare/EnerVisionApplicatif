import os
import httpx

MOCK_API_URL = os.environ.get("MOCK_API_URL", "http://10.105.200.45:8000")

_client = httpx.AsyncClient(base_url=MOCK_API_URL)


async def get_current_reading_raw(site_id: str) -> httpx.Response:
    return await _client.get(f"/api/v1/sites/{site_id}/current")


async def get_alerts_raw() -> httpx.Response:
    return await _client.get("/api/v1/alerts")


async def list_site_ids() -> list[str]:
    response = await _client.get("/api/v1/sites")
    response.raise_for_status()
    return [site["site_id"] for site in response.json()]
