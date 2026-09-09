from unittest.mock import patch

import pytest

from services.api_client import BackendUnavailableError
from services.measurement_service import (
    get_current_measurement,
    get_measurement_history,
)


# --- get_current_measurement -------------------------------------------

@patch("services.measurement_service.get")
def test_get_current_measurement_calls_expected_path_and_returns_json(mock_get):
    payload = {
        "consumption_kw": 87.34,
        "temperature_celsius": 22.1,
        "data_quality": "good",
    }
    mock_get.return_value = payload

    result = get_current_measurement("SITE001")

    mock_get.assert_called_once_with(
        "/api/v1/backend/sites/SITE001/current", timeout=10, allow_404=True
    )
    assert result == payload


@patch("services.measurement_service.get")
def test_get_current_measurement_returns_none_when_no_measurement(mock_get):
    mock_get.return_value = None

    assert get_current_measurement("SITE001") is None


@patch("services.measurement_service.get")
def test_get_current_measurement_propagates_backend_error(mock_get):
    mock_get.side_effect = BackendUnavailableError("boom")

    with pytest.raises(BackendUnavailableError):
        get_current_measurement("SITE001")


# --- get_measurement_history ---------------------------------------------

@patch("services.measurement_service.get")
def test_get_measurement_history_uses_default_pagination(mock_get):
    payload = [{"measurement_date": "2026-09-02T10:00:00", "consumption_kw": 80.1}]
    mock_get.return_value = payload

    result = get_measurement_history("SITE001")

    mock_get.assert_called_once_with(
        "/api/v1/backend/sites/SITE001/measurements",
        params={"limit": 100, "offset": 0},
        timeout=10,
    )
    assert result == payload


@patch("services.measurement_service.get")
def test_get_measurement_history_forwards_custom_pagination(mock_get):
    mock_get.return_value = []

    get_measurement_history("SITE001", limit=10, offset=20)

    mock_get.assert_called_once_with(
        "/api/v1/backend/sites/SITE001/measurements",
        params={"limit": 10, "offset": 20},
        timeout=10,
    )


@patch("services.measurement_service.get")
def test_get_measurement_history_propagates_backend_error(mock_get):
    mock_get.side_effect = BackendUnavailableError("site inconnu (404)")

    with pytest.raises(BackendUnavailableError):
        get_measurement_history("SITE999")
