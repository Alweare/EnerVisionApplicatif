import os

import requests

CORE_URL = os.environ["CORE_URL"]


def get_sites() -> list[dict]:
    response = requests.get(f"{CORE_URL}/api/v1/backend/sites", timeout=10)
    response.raise_for_status()
    return response.json()


def get_site(site_id: str) -> dict:
    response = requests.get(f"{CORE_URL}/api/v1/backend/sites/{site_id}", timeout=10)
    response.raise_for_status()
    return response.json()
