import os

import requests

BACKEND_URL = os.environ["BACKEND_URL"]


def get_current_measurement(site_id: str) -> dict | None:
    response = requests.get(
        f"{BACKEND_URL}/api/v1/backend/sites/{site_id}/current", timeout=10
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def get_measurement_history(site_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    response = requests.get(
        f"{BACKEND_URL}/api/v1/backend/sites/{site_id}/measurements",
        params={"limit": limit, "offset": offset},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
