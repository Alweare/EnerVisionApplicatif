"""Vérifie la configuration CORS de l'app (EN-171, dashboard Streamlit).

En test, aucune variable CORS_ALLOWED_ORIGINS n'est posée : l'app utilise donc
le défaut défini dans main.py (localhost:8501 / 127.0.0.1:8501).
"""

import pytest
from fastapi.testclient import TestClient

from core.main import app

client = TestClient(app)

ALLOWED_ORIGIN = "http://localhost:8501"
DISALLOWED_ORIGIN = "http://evil.example"


def test_preflight_from_allowed_origin_is_accepted():
    response = client.options(
        "/api/v1/backend/sites",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


def test_simple_request_from_allowed_origin_carries_cors_header():
    response = client.get("/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


def test_preflight_from_disallowed_origin_is_rejected():
    response = client.options(
        "/api/v1/backend/sites",
        headers={
            "Origin": DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", ["http://localhost:8501", "http://127.0.0.1:8501"])
def test_default_origins_are_all_allowed(origin):
    response = client.get("/health", headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin
