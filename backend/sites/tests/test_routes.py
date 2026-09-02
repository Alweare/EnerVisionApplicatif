import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.sites.repository import list_sites

client = TestClient(app)

SITE_FIELDS = {
    "site_id",
    "site_type",
    "site_name",
    "location",
    "capacity_kw",
    "status",
}


def test_get_sites_returns_200_with_all_sites():
    response = client.get("/api/v1/sites")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == len(list_sites())
    assert {site["site_id"] for site in body} == {"SITE001", "SITE002", "SITE003"}
    assert all(SITE_FIELDS == set(site.keys()) for site in body)


def test_get_site_by_id_returns_200_with_matching_site():
    response = client.get("/api/v1/sites/SITE002")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "site_id": "SITE002",
        "site_type": "factory",
        "site_name": "Usine Lyon Vénissieux",
        "location": "Lyon, France",
        "capacity_kw": 1000,
        "status": "active",
    }


@pytest.mark.parametrize("site_id", ["SITE001", "SITE002", "SITE003"])
def test_get_site_by_id_matches_repository_for_each_mock_site(site_id):
    response = client.get(f"/api/v1/sites/{site_id}")

    assert response.status_code == 200
    assert response.json()["site_id"] == site_id


def test_get_site_by_id_returns_404_when_unknown():
    response = client.get("/api/v1/sites/UNKNOWN")

    assert response.status_code == 404
    assert "UNKNOWN" in response.json()["detail"]
