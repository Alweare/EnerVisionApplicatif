from unittest.mock import patch

import pytest

from services.api_client import BackendUnavailableError
from services.site_service import get_my_sites, get_site, get_sites


# --- get_sites --------------------------------------------------------------

@patch("services.site_service.get")
def test_get_sites_calls_expected_url_and_returns_json(mock_get):
    payload = [{"site_id": "SITE001", "site_name": "Bureau Paris"}]
    mock_get.return_value = payload

    result = get_sites()

    mock_get.assert_called_once_with("/api/v1/sites", timeout=10)
    assert result == payload


@patch("services.site_service.get")
def test_get_sites_raises_when_backend_errors(mock_get):
    mock_get.side_effect = BackendUnavailableError("boom")

    with pytest.raises(BackendUnavailableError):
        get_sites()


# --- get_my_sites ----------------------------------------------------------

@patch("services.site_service.get")
def test_get_my_sites_calls_me_sites_endpoint(mock_get):
    payload = [{"site_id": "SITE001"}, {"site_id": "SITE003"}]
    mock_get.return_value = payload

    result = get_my_sites()

    mock_get.assert_called_once_with(
        "/api/v1/me/sites", params={"active_only": "true"}, timeout=10
    )
    assert result == payload


@patch("services.site_service.get")
def test_get_my_sites_forwards_active_only_false(mock_get):
    mock_get.return_value = []

    get_my_sites(active_only=False)

    mock_get.assert_called_once_with(
        "/api/v1/me/sites", params={"active_only": "false"}, timeout=10
    )


# --- get_site -----------------------------------------------------------

@patch("services.site_service.get")
def test_get_site_calls_expected_url_and_returns_json(mock_get):
    payload = {"site_id": "SITE001", "site_name": "Bureau Paris"}
    mock_get.return_value = payload

    result = get_site("SITE001")

    mock_get.assert_called_once_with("/api/v1/sites/SITE001", timeout=10)
    assert result == payload


@patch("services.site_service.get")
def test_get_site_raises_when_site_not_found(mock_get):
    mock_get.side_effect = BackendUnavailableError("boom")

    with pytest.raises(BackendUnavailableError):
        get_site("SITE999")
