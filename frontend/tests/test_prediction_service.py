from unittest.mock import Mock, patch

import pytest
import requests

from services.prediction_service import get_site_prediction

BACKEND_URL = "http://backend:8000"


def _mock_response(json_data=None, *, ok=True, status_code=200):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = json_data
    if ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = requests.HTTPError("boom")
    return response


@patch("services.prediction_service.requests.get")
def test_get_site_prediction_calls_expected_url_and_returns_json(mock_get):
    payload = {
        "site_id": "SITE001",
        "prediction": {"predicted_for": "2026-09-08T18:00:00", "predicted_consumption_kw": 145.0},
        "model": {"algorithm": "régression linéaire (scikit-learn)"},
        "history": [],
    }
    mock_get.return_value = _mock_response(payload)

    result = get_site_prediction("SITE001")

    mock_get.assert_called_once_with(
        f"{BACKEND_URL}/api/v1/backend/sites/SITE001/predictions",
        params={"history_hours": 24},
        timeout=10,
    )
    assert result == payload


@patch("services.prediction_service.requests.get")
def test_get_site_prediction_forwards_custom_history_hours(mock_get):
    mock_get.return_value = _mock_response({})

    get_site_prediction("SITE001", history_hours=48)

    mock_get.assert_called_once_with(
        f"{BACKEND_URL}/api/v1/backend/sites/SITE001/predictions",
        params={"history_hours": 48},
        timeout=10,
    )


@patch("services.prediction_service.requests.get")
def test_get_site_prediction_returns_none_when_site_unknown(mock_get):
    mock_get.return_value = _mock_response(status_code=404)

    assert get_site_prediction("SITE999") is None


@patch("services.prediction_service.requests.get")
def test_get_site_prediction_returns_none_when_no_prediction_available(mock_get):
    mock_get.return_value = _mock_response(status_code=503)

    assert get_site_prediction("SITE001") is None


@patch("services.prediction_service.requests.get")
def test_get_site_prediction_raises_on_server_error(mock_get):
    mock_get.return_value = _mock_response(ok=False, status_code=500)

    with pytest.raises(requests.HTTPError):
        get_site_prediction("SITE001")
