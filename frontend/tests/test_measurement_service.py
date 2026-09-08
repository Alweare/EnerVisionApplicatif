from unittest.mock import Mock, patch

import pytest
import requests

from services.measurement_service import (
    get_current_measurement,
    get_measurement_history,
)

CORE_URL = "http://core:8000"


def _mock_response(json_data=None, *, ok=True, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_data
    if ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = requests.HTTPError("boom")
    return response


# --- get_current_measurement -------------------------------------------

@patch("services.measurement_service.requests.get")
def test_get_current_measurement_calls_expected_url_and_returns_json(mock_get):
    payload = {
        "consumption_kw": 87.34,
        "temperature_celsius": 22.1,
        "data_quality": "good",
    }
    mock_get.return_value = _mock_response(payload)

    result = get_current_measurement("SITE001")

    mock_get.assert_called_once_with(
        f"{CORE_URL}/api/v1/backend/sites/SITE001/current", timeout=10
    )
    assert result == payload


@patch("services.measurement_service.requests.get")
def test_get_current_measurement_returns_none_when_no_measurement(mock_get):
    mock_get.return_value = _mock_response(status_code=404)

    assert get_current_measurement("SITE001") is None


@patch("services.measurement_service.requests.get")
def test_get_current_measurement_raises_on_server_error(mock_get):
    mock_get.return_value = _mock_response(ok=False, status_code=500)

    with pytest.raises(requests.HTTPError):
        get_current_measurement("SITE001")


# --- get_measurement_history ---------------------------------------------

@patch("services.measurement_service.requests.get")
def test_get_measurement_history_uses_default_pagination(mock_get):
    payload = [{"measurement_date": "2026-09-02T10:00:00", "consumption_kw": 80.1}]
    mock_get.return_value = _mock_response(payload)

    result = get_measurement_history("SITE001")

    mock_get.assert_called_once_with(
        f"{CORE_URL}/api/v1/backend/sites/SITE001/measurements",
        params={"limit": 100, "offset": 0},
        timeout=10,
    )
    assert result == payload


@patch("services.measurement_service.requests.get")
def test_get_measurement_history_forwards_custom_pagination(mock_get):
    mock_get.return_value = _mock_response([])

    get_measurement_history("SITE001", limit=10, offset=20)

    mock_get.assert_called_once_with(
        f"{CORE_URL}/api/v1/backend/sites/SITE001/measurements",
        params={"limit": 10, "offset": 20},
        timeout=10,
    )


@patch("services.measurement_service.requests.get")
def test_get_measurement_history_raises_when_site_not_found(mock_get):
    mock_get.return_value = _mock_response(ok=False)

    with pytest.raises(requests.HTTPError):
        get_measurement_history("SITE999")
