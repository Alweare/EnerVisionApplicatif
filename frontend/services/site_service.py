import os

from services.api_client import get



def get_sites() -> list[dict]:
    return get("/api/v1/sites", timeout=10)


def get_my_sites() -> list[dict]:
    return get("/api/v1/me/sites", timeout=10)


def get_site(site_id: str) -> dict:
    return get(f"/api/v1/sites/{site_id}", timeout=10)