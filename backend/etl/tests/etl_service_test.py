import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from etl.service.etl_service import ETLService

def make_service_with_mock():
    service = ETLService.__new__(ETLService)
    service.measurement_service = Mock()
    service.file_tracking_service = Mock()
    service.container_client = Mock()
    service.db = Mock()
    service.db.begin_nested.return_value.__enter__ = Mock()
    service.db.begin_nested.return_value.__exit__ = Mock(return_value=False)
    service.measurement_service.measurement_exists.return_value = False
    service.lookback_minutes = 3
    return service

def make_blob(name, minutes_ago):
    return SimpleNamespace(
        name=name,
        last_modified=datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    )

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

def test_load_adds_measurement_without_commit():
    service = make_service_with_mock()
    measurement = Mock()

    service.load(measurement)

    service.measurement_service.add_measurement.assert_called_once_with(measurement)
    service.db.commit.assert_not_called()


# --- Étape 2 : filtrage temporel sur last_modified ------------------------

def test_list_recent_blob_paths_keeps_only_blobs_within_window():
    service = make_service_with_mock()
    service.container_client.list_blobs.return_value = [
        make_blob("measures/old.json", minutes_ago=10),
        make_blob("measures/recent.json", minutes_ago=1),
    ]

    paths = service.list_recent_blob_paths()

    assert paths == ["measures/recent.json"]
    # Une fenêtre de 3 minutes ne couvre qu'un jour : un seul préfixe listé.
    service.container_client.list_blobs.assert_called_once_with(
        name_starts_with=f"measures/{datetime.now(timezone.utc):%Y/%m/%d}/"
    )

def test_list_recent_blob_paths_sorts_chronologically():
    service = make_service_with_mock()
    service.lookback_minutes = 3
    service.container_client.list_blobs.return_value = [
        make_blob("measures/b.json", minutes_ago=1),
        make_blob("measures/a.json", minutes_ago=2),
    ]

    paths = service.list_recent_blob_paths()

    assert paths == ["measures/a.json", "measures/b.json"]

def test_list_recent_blob_paths_uses_explicit_window_over_default():
    service = make_service_with_mock()
    service.lookback_minutes = 3
    service.container_client.list_blobs.return_value = [
        make_blob("measures/old.json", minutes_ago=30),
    ]

    assert service.list_recent_blob_paths() == []
    assert service.list_recent_blob_paths(lookback_minutes=60) == ["measures/old.json"]


# --- Étape 3 : dédoublonnage ---------------------------------------------

def test_run_processes_only_files_not_already_tracked():
    service = make_service_with_mock()
    service.list_recent_blob_paths = Mock(
        return_value=["measures/a.json", "measures/b.json"]
    )
    service.file_tracking_service.filter_new_files.return_value = ["measures/b.json"]
    service.process_batch = Mock()

    service.run()

    service.file_tracking_service.filter_new_files.assert_called_once_with(
        ["measures/a.json", "measures/b.json"]
    )
    service.process_batch.assert_called_once_with(["measures/b.json"])

def test_run_does_nothing_when_no_recent_file():
    service = make_service_with_mock()
    service.list_recent_blob_paths = Mock(return_value=[])
    service.process_batch = Mock()

    service.run()

    service.process_batch.assert_not_called()
    service.file_tracking_service.filter_new_files.assert_not_called()


# --- Étape 4 : insertion transactionnelle --------------------------------

def test_process_batch_commits_once_for_all_files():
    service = make_service_with_mock()
    service.download_readings = Mock(side_effect=lambda path: [
        {"site_id": "SITE001", "reading": path}
    ])
    measurements = {
        "measures/a.json": Mock(site_id="SITE001", measurement_date=1),
        "measures/b.json": Mock(site_id="SITE001", measurement_date=2),
    }
    service.transform = Mock(side_effect=lambda site_id, reading: measurements[reading["reading"]])
    service.load = Mock()

    assert service.process_batch(["measures/a.json", "measures/b.json"]) is True

    assert service.load.call_count == 2
    service.load.assert_any_call(measurements["measures/a.json"])
    service.load.assert_any_call(measurements["measures/b.json"])

def test_process_batch_rolls_back_everything_when_commit_fails():
    service = make_service_with_mock()
    service.download_readings = Mock(return_value=[{"site_id": "SITE001"}])
    service._site_exists = Mock(return_value=True)
    service.transform = Mock(return_value="measurement")
    service.load = Mock()
    service.db.commit.side_effect = SQLAlchemyError("connexion perdue")

    assert service.process_batch(["measures/a.json"]) is False

    service.db.rollback.assert_called_once()

def test_process_batch_skips_failing_file_and_keeps_the_rest():
    service = make_service_with_mock()
    service.download_readings = Mock(side_effect=[
        OSError("azure indisponible"),
        [{"site_id": "SITE001", "reading": "ok"}],
    ])
    service._site_exists = Mock(return_value=True)
    service.transform = Mock(return_value=Mock(site_id="SITE001", measurement_date=1))
    service.load = Mock()

    assert service.process_batch(["measures/ko.json", "measures/ok.json"]) is True

    # Seul le fichier lisible est tracé ; l'autre sera rejoué.
    service.file_tracking_service.mark_processed.assert_called_once_with("measures/ok.json")
    service.db.commit.assert_called_once()

def test_stage_blob_skips_reading_without_site_id_but_still_tracks_file():
    service = make_service_with_mock()
    service.download_readings = Mock(return_value=[{"consumption_kw": 12.0}])
    service._site_exists = Mock(return_value=True)
    service.transform = Mock()
    service.load = Mock()

    assert service.stage_blob("measures/a.json") == 0

    service.transform.assert_not_called()
    service.load.assert_not_called()

def test_start_continuous_run_loops_then_stops(monkeypatch):
    service = make_service_with_mock()
    service.run = Mock()

    calls = {"n": 0}
    def fake_sleep(_interval):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise KeyboardInterrupt
    monkeypatch.setattr("etl.service.etl_service.time.sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        service.start_continuous_run(interval=0)

    assert service.run.call_count == 2

def test_start_continuous_run_logs_error_and_keeps_going(monkeypatch):
    service = make_service_with_mock()
    service.run = Mock(side_effect=RuntimeError("boom"))

    def fake_sleep(_interval):
        raise KeyboardInterrupt
    monkeypatch.setattr("etl.service.etl_service.time.sleep", fake_sleep)

    with pytest.raises(KeyboardInterrupt):
        service.start_continuous_run(interval=0)

    service.run.assert_called_once()
