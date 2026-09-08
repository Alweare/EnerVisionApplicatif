"""Tests de services/alert_service.py — appels HTTP vers /api/v1/backend/alerts."""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
import requests

from services.alert_service import get_alerts

BACKEND_URL = "http://backend:8000"
ALERTS_URL = f"{BACKEND_URL}/api/v1/backend/alerts"


def _mock_response(json_data=None, *, ok=True):
    response = Mock()
    response.json.return_value = json_data
    if ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = requests.HTTPError("boom")
    return response


@patch("services.alert_service.requests.get")
def test_get_alerts_without_site_omits_the_filter(mock_get):
    payload = [{"alert_id": "ALR-SITE001-1", "site_id": "SITE001"}]
    mock_get.return_value = _mock_response(payload)

    result = get_alerts()

    mock_get.assert_called_once_with(
        ALERTS_URL, params={"limit": 100, "offset": 0}, timeout=10
    )
    assert result == payload


@patch("services.alert_service.requests.get")
def test_get_alerts_forwards_the_site_filter(mock_get):
    mock_get.return_value = _mock_response([])

    get_alerts(site_id="SITE002")

    mock_get.assert_called_once_with(
        ALERTS_URL,
        params={"limit": 100, "offset": 0, "site_id": "SITE002"},
        timeout=10,
    )


@patch("services.alert_service.requests.get")
def test_get_alerts_forwards_pagination(mock_get):
    mock_get.return_value = _mock_response([])

    get_alerts(limit=5, offset=20)

    mock_get.assert_called_once_with(
        ALERTS_URL, params={"limit": 5, "offset": 20}, timeout=10
    )


@patch("services.alert_service.requests.get")
def test_get_alerts_returns_empty_list_when_no_alert(mock_get):
    mock_get.return_value = _mock_response([])

    assert get_alerts() == []


@patch("services.alert_service.requests.get")
def test_get_alerts_raises_when_backend_errors(mock_get):
    mock_get.return_value = _mock_response(ok=False)

    with pytest.raises(requests.HTTPError):
        get_alerts()


@patch("services.alert_service.requests.get")
def test_get_alerts_forwards_the_since_bound(mock_get):
    mock_get.return_value = _mock_response([])

    get_alerts(since=datetime(2026, 8, 9, 12, 0))

    mock_get.assert_called_once_with(
        ALERTS_URL,
        params={"limit": 100, "offset": 0, "since": "2026-08-09T12:00:00"},
        timeout=10,
    )


@patch("services.alert_service.requests.get")
def test_get_alerts_keeps_the_timezone_in_the_since_bound(mock_get):
    mock_get.return_value = _mock_response([])

    get_alerts(since=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc))

    envoye = mock_get.call_args.kwargs["params"]["since"]
    assert envoye == "2026-08-09T12:00:00+00:00"


# --- filtre de gravité -----------------------------------------------------

@patch("services.alert_service.requests.get")
def test_get_alerts_forwards_the_selected_severities(mock_get):
    mock_get.return_value = _mock_response([])

    get_alerts(severities=["high", "critical"])

    mock_get.assert_called_once_with(
        ALERTS_URL,
        params={"limit": 100, "offset": 0, "severity": ["high", "critical"]},
        timeout=10,
    )


@patch("services.alert_service.requests.get")
def test_get_alerts_omits_an_empty_severity_list(mock_get):
    mock_get.return_value = _mock_response([])

    get_alerts(severities=[])

    assert "severity" not in mock_get.call_args.kwargs["params"]


@patch("services.alert_service.requests.get")
def test_get_alerts_combines_site_and_severity_filters(mock_get):
    mock_get.return_value = _mock_response([])

    get_alerts(site_id="SITE002", severities=["low"])

    assert mock_get.call_args.kwargs["params"] == {
        "limit": 100,
        "offset": 0,
        "site_id": "SITE002",
        "severity": ["low"],
    }
