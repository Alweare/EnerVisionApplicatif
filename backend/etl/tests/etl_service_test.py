from datetime import datetime
from unittest.mock import Mock

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy.exc import SQLAlchemyError

from etl.service.alert_service import AlertService
from etl.service.etl_service import ETLService

def make_service_with_mock():
    service = ETLService.__new__(ETLService)
    service.measurement_service = Mock()
    return service

def test_forward_fill_returns_unchanged_when_nothing_missing():
    service = make_service_with_mock()
    reading = {
        "consumption_kw": 87.34, "consumption_kwh": 87.34, "voltage_v": 401.2,
        "current_a": 132.5, "power_factor": 0.923, "temperature_celsius": 22.1,
        "humidity_percent": 58.4,
    }

    cleaned = service.forward_fill("SITE001", reading)

    assert cleaned == reading
    service.measurement_service.get_last_measurement.assert_not_called()

def test_forward_fill_fills_missing_field_from_last_measurement():
    service = make_service_with_mock()
    last = Mock(temperature_celsius=20.0, humidity_percent=50.0)
    service.measurement_service.get_last_measurement.return_value = last

    reading = {
        "consumption_kw": 87.34, "consumption_kwh": 87.34, "voltage_v": 401.2,
        "current_a": 132.5, "power_factor": 0.923,
        "temperature_celsius": None, "humidity_percent": None,
    }

    cleaned = service.forward_fill("SITE001", reading)

    assert cleaned["temperature_celsius"] == 20.0
    assert cleaned["humidity_percent"] == 50.0
    assert cleaned["consumption_kw"] == 87.34  # not changed

def test_forward_fill_keeps_null_when_no_previous_measurement():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurement.return_value = None

    reading = {"consumption_kw": 87.34, "temperature_celsius": None}

    cleaned = service.forward_fill("SITE001", reading)

    assert cleaned["temperature_celsius"] is None

def test_forward_fill_does_not_mutate_original_reading():
    service = make_service_with_mock()
    last = Mock(temperature_celsius=20.0)
    service.measurement_service.get_last_measurement.return_value = last

    reading = {"consumption_kw": 87.34, "temperature_celsius": None}
    service.forward_fill("SITE001", reading)

    assert reading["temperature_celsius"] is None  # original has not change

def test_transform_builds_measurement_from_cleaned_reading():
    service = make_service_with_mock()
    service.measurement_service.get_last_measurement.return_value = None
    expected_measurement = Mock()
    service.measurement_service.build_measurement.return_value = expected_measurement

    reading = {"consumption_kw": 87.34, "timestamp": datetime.now()}
    result = service.transform("SITE001", reading)

    assert result is expected_measurement
    service.measurement_service.build_measurement.assert_called_once()

def test_load_calls_save_with_measurement():
    service = make_service_with_mock()
    measurement = Mock()

    service.load(measurement)

    service.measurement_service.save_measurement.assert_called_once_with(measurement)

def test_run_processes_each_reading():
    service = make_service_with_mock()
    # Mock de la base de données pour que la vérification du site réussisse
    service.db = Mock()
    service.db.query().filter().scalar.return_value = "SITE001"

    service.extract_all = Mock(return_value=[
        {"site_id": "SITE001", "reading": 1},
        {"site_id": "SITE001", "reading": 2}
    ])
    service.transform = Mock(side_effect=lambda site_id, reading: f"measurement-{reading['reading']}")
    service.load = Mock()

    service.run()

    assert service.transform.call_count == 2
    assert service.load.call_count == 2
    service.load.assert_any_call("measurement-1")
    service.load.assert_any_call("measurement-2")

def test_run_does_nothing_when_no_readings():
    service = make_service_with_mock()
    service.extract_all = Mock(return_value=[])
    service.transform = Mock()
    service.load = Mock()

    service.run()

    service.transform.assert_not_called()
    service.load.assert_not_called()

# --- Alertes ---------------------------------------------------------------

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


def make_alert_service_with_mock(known_sites=("SITE001", "SITE002")):
    service = ETLService.__new__(ETLService)
    service.db = Mock()
    service.db.query.return_value.all.return_value = [(s,) for s in known_sites]
    service.alert_service = AlertService.__new__(AlertService)
    service.alert_service.repository = Mock()
    service.alert_service.repository.add.side_effect = len
    service.file_tracking_service = Mock()
    service.file_tracking_service.filter_new_files.side_effect = lambda paths: paths
    return service


def make_container_client_with(blobs: dict, minutes_ago: int = 1):
    now = datetime.now(timezone.utc)
    container_client = Mock()
    container_client.list_blobs.return_value = [
        SimpleNamespace(name=name, last_modified=now - timedelta(minutes=minutes_ago))
        for name in blobs
    ]

    def get_blob_client(name):
        client = Mock()
        client.download_blob.return_value.readall.return_value = blobs[name].encode()
        return client

    container_client.get_blob_client.side_effect = get_blob_client
    return container_client


def test_default_lookback_window_covers_a_full_day():
    from etl.service.etl_service import DEFAULT_LOOKBACK_MINUTES

    assert DEFAULT_LOOKBACK_MINUTES == 24 * 60


def make_alert_service_with_mock(known_sites=("SITE001", "SITE002")):
    service = ETLService.__new__(ETLService)
    service.db = Mock()
    service.db.query.return_value.all.return_value = [(s,) for s in known_sites]
    service.db.begin_nested.return_value.__enter__ = Mock()
    service.db.begin_nested.return_value.__exit__ = Mock(return_value=False)
    service.alert_service = AlertService.__new__(AlertService)
    service.alert_service.repository = Mock()
    service.alert_service.repository.add.side_effect = len
    service.file_tracking_service = Mock()
    service.file_tracking_service.filter_new_files.side_effect = lambda paths: paths
    return service


def test_stage_alert_blob_inserts_and_tracks_the_file():
    service = make_alert_service_with_mock()
    service.download_alerts = Mock(return_value=[RAW_ALERT])

    assert service.stage_alert_blob("alert/a.json") == 1

    service.file_tracking_service.mark_processed.assert_called_once_with("alert/a.json")
    service.db.commit.assert_not_called()


def test_stage_alert_blob_skips_alerts_of_unknown_sites():
    service = make_alert_service_with_mock(known_sites=("SITE001",))
    service.download_alerts = Mock(return_value=[RAW_ALERT])  # SITE002 inconnu

    assert service.stage_alert_blob("alert/a.json") == 0
    assert service.alert_service.repository.add.call_args[0][0] == []


def test_stage_alert_blob_skips_alerts_without_an_id():
    service = make_alert_service_with_mock()
    incomplete = {k: v for k, v in RAW_ALERT.items() if k != "alert_id"}
    service.download_alerts = Mock(return_value=[incomplete])

    assert service.stage_alert_blob("alert/a.json") == 0


def test_run_alerts_processes_each_new_blob_then_commits_once():
    service = make_alert_service_with_mock()
    service.list_recent_alert_blobs = Mock(
        return_value=["alert/a.json", "alert/b.json"]
    )
    service.stage_alert_blob = Mock(return_value=1)

    assert service.run_alerts() == 2
    assert service.stage_alert_blob.call_count == 2
    service.db.commit.assert_called_once()


def test_run_alerts_ignores_blobs_already_tracked():
    service = make_alert_service_with_mock()
    service.list_recent_alert_blobs = Mock(
        return_value=["alert/vu.json", "alert/neuf.json"]
    )
    service.file_tracking_service.filter_new_files.side_effect = None
    service.file_tracking_service.filter_new_files.return_value = ["alert/neuf.json"]
    service.stage_alert_blob = Mock(return_value=1)

    assert service.run_alerts() == 1
    service.stage_alert_blob.assert_called_once_with("alert/neuf.json")


def test_run_alerts_skips_a_failing_blob_and_keeps_the_others():
    service = make_alert_service_with_mock()
    service.list_recent_alert_blobs = Mock(return_value=["alert/ko.json", "alert/ok.json"])
    service.stage_alert_blob = Mock(side_effect=[ValueError("json invalide"), 1])

    assert service.run_alerts() == 1
    service.db.commit.assert_called_once()


def test_run_alerts_does_nothing_when_every_blob_is_tracked():
    service = make_alert_service_with_mock()
    service.list_recent_alert_blobs = Mock(return_value=["alert/vu.json"])
    service.file_tracking_service.filter_new_files.side_effect = None
    service.file_tracking_service.filter_new_files.return_value = []
    service.stage_alert_blob = Mock()

    assert service.run_alerts() == 0
    service.stage_alert_blob.assert_not_called()
    service.db.commit.assert_not_called()


def test_list_recent_alert_blobs_ignores_blobs_outside_the_window(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "raw")
    service = ETLService.__new__(ETLService)
    service.lookback_minutes = 24 * 60
    now = datetime.now(timezone.utc)
    container_client = Mock()
    container_client.list_blobs.return_value = [
        SimpleNamespace(name="alert/vieux.json", last_modified=now - timedelta(days=3)),
        SimpleNamespace(name="alert/recent.json", last_modified=now - timedelta(minutes=5)),
    ]
    service.container_client = container_client

    assert service.list_recent_alert_blobs() == ["alert/recent.json"]
    container_client.list_blobs.assert_called_once_with(name_starts_with="alert/")


def test_download_alerts_accepts_a_list_or_a_single_object(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "raw")
    service = ETLService.__new__(ETLService)
    container_client = Mock()

    def blob_returning(payload):
        client = Mock()
        client.download_blob.return_value.readall.return_value = json.dumps(payload).encode()
        return client

    service.container_client = container_client

    container_client.get_blob_client.return_value = blob_returning([RAW_ALERT])
    assert service.download_alerts("alert/a.json") == [RAW_ALERT]

    container_client.get_blob_client.return_value = blob_returning(RAW_ALERT)
    assert service.download_alerts("alert/a.json") == [RAW_ALERT]
