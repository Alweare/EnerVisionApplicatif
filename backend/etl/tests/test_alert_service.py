from unittest.mock import Mock

import pytest

from etl.service.alert_service import AlertService

RAW_ALERT = {
    "alert_id": "ALR-SITE002-1718458320",
    "timestamp": "2024-06-15T14:12:00",
    "site_id": "SITE002",
    "severity": "critical",
    "type": "outage",
    "message": "Risque de surcharge sur Usine Lyon Vénissieux",
    "value": 812.5,
    "threshold": 720.0,
}


@pytest.fixture
def alert_service():
    service = AlertService.__new__(AlertService)
    service.repository = Mock()
    return service


def test_build_alert_maps_every_field(alert_service):
    alert = alert_service.build_alert(RAW_ALERT)

    assert alert["alert_id"] == "ALR-SITE002-1718458320"
    assert alert["site_id"] == "SITE002"
    assert alert["severity"] == "critical"
    assert alert["type"] == "outage"
    assert alert["message"] == "Risque de surcharge sur Usine Lyon Vénissieux"
    assert alert["value"] == 812.5
    assert alert["threshold"] == 720.0


def test_build_alert_maps_api_timestamp_to_created_at(alert_service):
    alert = alert_service.build_alert(RAW_ALERT)

    assert alert["created_at"] == "2024-06-15T14:12:00"
    assert "timestamp" not in alert


def test_build_alert_tolerates_optional_fields_absent(alert_service):
    alert = alert_service.build_alert({"alert_id": "ALR-1", "site_id": "SITE001"})

    assert alert["severity"] is None
    assert alert["value"] is None
    assert alert["created_at"] is None


def test_is_valid_accepts_a_complete_alert(alert_service):
    assert alert_service.is_valid(RAW_ALERT) is True


@pytest.mark.parametrize("missing", ["alert_id", "site_id"])
def test_is_valid_rejects_an_alert_without_its_keys(alert_service, missing):
    incomplete = {k: v for k, v in RAW_ALERT.items() if k != missing}

    assert alert_service.is_valid(incomplete) is False


def test_save_all_delegates_to_the_repository(alert_service):
    alert_service.repository.add.return_value = 2
    alerts = [{"alert_id": "ALR-1"}, {"alert_id": "ALR-2"}]

    assert alert_service.save_all(alerts) == 2
    alert_service.repository.add.assert_called_once_with(alerts)
