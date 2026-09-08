from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from core.api.schemas import AlertRead
from core.api.service.alert_service import AlertService, SiteNotFoundError


@pytest.fixture
def alert_service():
    service = AlertService.__new__(AlertService)
    service.repository = Mock()
    service.site_repository = Mock()
    return service


def _alert(site_id: str = "SITE001", alert_id: str = "ALR-SITE001-1") -> AlertRead:
    return AlertRead(
        alert_id=alert_id,
        site_id=site_id,
        severity="critical",
        type="spike",
        message="Pic de consommation détecté",
        value=812.5,
        threshold=720.0,
        created_at=datetime(2026, 9, 7, 15, 18, 29),
    )


# --- sans filtre : toutes les alertes -------------------------------------

def test_list_alerts_without_site_returns_every_alert(alert_service):
    alerts = [_alert("SITE001"), _alert("SITE002", "ALR-SITE002-1")]
    alert_service.repository.list_all.return_value = alerts

    result = alert_service.list_alerts()

    assert result == alerts
    assert all(isinstance(a, AlertRead) for a in result)
    alert_service.repository.list_all.assert_called_once_with(
        limit=100, offset=0, since=None, severities=None
    )


def test_list_alerts_without_site_never_checks_the_site_exists(alert_service):
    alert_service.repository.list_all.return_value = []

    alert_service.list_alerts()

    alert_service.site_repository.exists.assert_not_called()


def test_list_alerts_forwards_pagination(alert_service):
    alert_service.repository.list_all.return_value = []

    alert_service.list_alerts(limit=5, offset=20)

    alert_service.repository.list_all.assert_called_once_with(
        limit=5, offset=20, since=None, severities=None
    )


def test_list_alerts_returns_empty_list_when_no_alert(alert_service):
    alert_service.repository.list_all.return_value = []

    assert alert_service.list_alerts() == []


# --- avec filtre : alertes d'un site --------------------------------------

def test_list_alerts_for_a_site_filters_on_that_site(alert_service):
    alerts = [_alert("SITE002", "ALR-SITE002-1")]
    alert_service.site_repository.exists.return_value = True
    alert_service.repository.list_by_site.return_value = alerts

    result = alert_service.list_alerts(site_id="SITE002")

    assert result == alerts
    alert_service.repository.list_by_site.assert_called_once_with(
        "SITE002", limit=100, offset=0, since=None, severities=None
    )
    alert_service.repository.list_all.assert_not_called()


def test_list_alerts_for_a_site_forwards_pagination(alert_service):
    alert_service.site_repository.exists.return_value = True
    alert_service.repository.list_by_site.return_value = []

    alert_service.list_alerts(site_id="SITE002", limit=5, offset=20)

    alert_service.repository.list_by_site.assert_called_once_with(
        "SITE002", limit=5, offset=20, since=None, severities=None
    )


def test_list_alerts_raises_when_the_site_is_unknown(alert_service):
    alert_service.site_repository.exists.return_value = False

    with pytest.raises(SiteNotFoundError):
        alert_service.list_alerts(site_id="SITE999")

    alert_service.repository.list_by_site.assert_not_called()


def test_list_alerts_returns_empty_list_for_a_site_without_alert(alert_service):
    alert_service.site_repository.exists.return_value = True
    alert_service.repository.list_by_site.return_value = []

    assert alert_service.list_alerts(site_id="SITE001") == []


# --- fenêtre temporelle ----------------------------------------------------

def test_list_alerts_forwards_the_since_bound(alert_service):
    since = datetime(2026, 8, 9, 12, 0)
    alert_service.repository.list_all.return_value = []

    alert_service.list_alerts(since=since)

    alert_service.repository.list_all.assert_called_once_with(
        limit=100, offset=0, since=since, severities=None
    )


def test_list_alerts_forwards_the_since_bound_for_a_site(alert_service):
    since = datetime(2026, 8, 9, 12, 0)
    alert_service.site_repository.exists.return_value = True
    alert_service.repository.list_by_site.return_value = []

    alert_service.list_alerts(site_id="SITE002", since=since)

    alert_service.repository.list_by_site.assert_called_once_with(
        "SITE002", limit=100, offset=0, since=since, severities=None
    )


def test_list_alerts_converts_an_aware_bound_to_naive_utc(alert_service):
    aware = datetime(2026, 8, 9, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    alert_service.repository.list_all.return_value = []

    alert_service.list_alerts(since=aware)

    passed = alert_service.repository.list_all.call_args.kwargs["since"]
    assert passed == datetime(2026, 8, 9, 12, 0)
    assert passed.tzinfo is None


# --- filtre de gravité -----------------------------------------------------

def test_list_alerts_forwards_the_selected_severities(alert_service):
    alert_service.repository.list_all.return_value = []

    alert_service.list_alerts(severities=["high", "critical"])

    alert_service.repository.list_all.assert_called_once_with(
        limit=100, offset=0, since=None, severities=["high", "critical"]
    )


def test_list_alerts_forwards_the_selected_severities_for_a_site(alert_service):
    alert_service.site_repository.exists.return_value = True
    alert_service.repository.list_by_site.return_value = []

    alert_service.list_alerts(site_id="SITE002", severities=["low"])

    alert_service.repository.list_by_site.assert_called_once_with(
        "SITE002", limit=100, offset=0, since=None, severities=["low"]
    )


def test_list_alerts_treats_an_empty_severity_list_as_no_filter(alert_service):
    alert_service.repository.list_all.return_value = []

    alert_service.list_alerts(severities=[])

    alert_service.repository.list_all.assert_called_once_with(
        limit=100, offset=0, since=None, severities=None
    )
