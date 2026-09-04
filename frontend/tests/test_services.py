"""Tests de la couche services du frontend.

Aujourd'hui les services renvoient des mocks (pas encore d'appel HTTP réel
au backend). Ces tests figent la forme des données consommées par les pages
Streamlit ; à étoffer quand les vrais appels au backend (BACKEND_URL + CORS,
cf. EN-171) remplaceront les mocks.
"""

from services.measurement_service import (
    get_current_measurement,
    get_measurement_history,
)
from services.site_service import get_sites


def test_get_sites_returns_non_empty_list():
    sites = get_sites()

    assert isinstance(sites, list)
    assert len(sites) > 0
    assert {"site_id", "site_name", "capacity_kw"} <= sites[0].keys()


def test_get_current_measurement_returns_expected_shape():
    current = get_current_measurement("SITE001")

    assert set(current) == {"consumption_kw", "temperature_celsius", "data_quality"}


def test_get_measurement_history_returns_series():
    history = get_measurement_history("SITE001")

    assert isinstance(history, list) and len(history) > 0
    assert all("consumption_kw" in row for row in history)
