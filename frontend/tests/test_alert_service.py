"""Tests de services/alert_service.py — appels vers /api/v1/backend/alerts."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from services.api_client import BackendUnavailableError
from services.alert_service import get_alerts

ALERTS_PATH = "/api/v1/backend/alerts"


@patch("services.alert_service.get")
def test_get_alerts_without_filter_asks_for_every_alert(mock_get):
    payload = [{"alert_id": "ALR-SITE001-1", "site_id": "SITE001"}]
    mock_get.return_value = payload

    result = get_alerts()

    mock_get.assert_called_once_with(
        ALERTS_PATH, params={"limit": 100, "offset": 0}, timeout=10
    )
    assert result == payload


@patch("services.alert_service.get")
def test_get_alerts_forwards_the_site_filter(mock_get):
    mock_get.return_value = []

    get_alerts(site_id="SITE002")

    assert mock_get.call_args.kwargs["params"]["site_id"] == "SITE002"


@patch("services.alert_service.get")
def test_get_alerts_forwards_pagination(mock_get):
    mock_get.return_value = []

    get_alerts(limit=5, offset=20)

    mock_get.assert_called_once_with(
        ALERTS_PATH, params={"limit": 5, "offset": 20}, timeout=10
    )


@patch("services.alert_service.get")
def test_get_alerts_returns_empty_list_when_no_alert(mock_get):
    mock_get.return_value = []

    assert get_alerts() == []


@patch("services.alert_service.get")
def test_get_alerts_propagates_a_backend_failure(mock_get):
    mock_get.side_effect = BackendUnavailableError("boom")

    with pytest.raises(BackendUnavailableError):
        get_alerts()


# --- fenêtre temporelle ----------------------------------------------------

@patch("services.alert_service.get")
def test_get_alerts_forwards_the_since_bound(mock_get):
    mock_get.return_value = []

    get_alerts(since=datetime(2026, 8, 9, 12, 0))

    assert mock_get.call_args.kwargs["params"]["since"] == "2026-08-09T12:00:00"


@patch("services.alert_service.get")
def test_get_alerts_keeps_the_timezone_in_the_since_bound(mock_get):
    mock_get.return_value = []

    get_alerts(since=datetime(2026, 8, 9, 12, 0, tzinfo=timezone.utc))

    assert mock_get.call_args.kwargs["params"]["since"] == "2026-08-09T12:00:00+00:00"


# --- filtre de gravité -----------------------------------------------------

@patch("services.alert_service.get")
def test_get_alerts_forwards_the_selected_severities(mock_get):
    mock_get.return_value = []

    get_alerts(severities=["high", "critical"])

    assert mock_get.call_args.kwargs["params"]["severity"] == ["high", "critical"]


@patch("services.alert_service.get")
def test_get_alerts_omits_an_empty_severity_list(mock_get):
    # Rien de coché = toutes les gravités : on n'envoie pas le paramètre.
    mock_get.return_value = []

    get_alerts(severities=[])

    assert "severity" not in mock_get.call_args.kwargs["params"]


@patch("services.alert_service.get")
def test_get_alerts_combines_site_and_severity_filters(mock_get):
    mock_get.return_value = []

    get_alerts(site_id="SITE002", severities=["low"])

    assert mock_get.call_args.kwargs["params"] == {
        "limit": 100,
        "offset": 0,
        "site_id": "SITE002",
        "severity": ["low"],
    }
