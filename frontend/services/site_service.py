import os

import requests

BACKEND_URL = os.environ["BACKEND_URL"]


def get_sites() -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/api/v1/backend/sites", timeout=10)
    response.raise_for_status()
    return response.json()


def get_site(site_id: str) -> dict:
    response = requests.get(f"{BACKEND_URL}/api/v1/backend/sites/{site_id}", timeout=10)
    response.raise_for_status()
    return response.json()
