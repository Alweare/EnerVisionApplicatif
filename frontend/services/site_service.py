import os

BACKEND_URL = os.environ["BACKEND_URL"]

MOCK_SITES = [
    {
        "site_id": "SITE001",
        "site_type": "office",
        "site_name": "Bureau Paris La Défense",
        "location": "Paris, France",
        "capacity_kw": 200,
        "status": "active",
    },
    {
        "site_id": "SITE002",
        "site_type": "factory",
        "site_name": "Usine Lyon Vénissieux",
        "location": "Lyon, France",
        "capacity_kw": 1000,
        "status": "active",
    },
    {
        "site_id": "SITE003",
        "site_type": "datacenter",
        "site_name": "Data Center Marseille",
        "location": "Marseille, France",
        "capacity_kw": 800,
        "status": "active",
    },
]

def get_sites() -> list[dict]:
        return MOCK_SITES