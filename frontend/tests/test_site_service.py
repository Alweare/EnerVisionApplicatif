from unittest.mock import Mock, patch

import pytest
import requests

from services.site_service import get_site, get_sites

BACKEND_URL = "http://backend:8000"


def _mock_response(json_data=None, *, ok=True):
    response = Mock()
    response.json.return_value = json_data
    if ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = requests.HTTPError("boom")
    return response


# --- get_sites --------------------------------------------------------------

@patch("services.site_service.requests.get")
def test_get_sites_calls_expected_url_and_returns_json(mock_get):
    payload = [{"site_id": "SITE001", "site_name": "Bureau Paris"}]
    mock_get.return_value = _mock_response(payload)

    result = get_sites()

    mock_get.assert_called_once_with(f"{BACKEND_URL}/api/v1/backend/sites", timeout=10)
    assert result == payload


@patch("services.site_service.requests.get")
def test_get_sites_raises_when_backend_errors(mock_get):
    mock_get.return_value = _mock_response(ok=False)

    with pytest.raises(requests.HTTPError):
        get_sites()


# --- get_site -----------------------------------------------------------

@patch("services.site_service.requests.get")
def test_get_site_calls_expected_url_and_returns_json(mock_get):
    payload = {"site_id": "SITE001", "site_name": "Bureau Paris"}
    mock_get.return_value = _mock_response(payload)

    result = get_site("SITE001")

    mock_get.assert_called_once_with(
        f"{BACKEND_URL}/api/v1/backend/sites/SITE001", timeout=10
    )
    assert result == payload


@patch("services.site_service.requests.get")
def test_get_site_raises_when_site_not_found(mock_get):
    mock_get.return_value = _mock_response(ok=False)

    with pytest.raises(requests.HTTPError):
        get_site("SITE999")
