import json
from datetime import datetime
from unittest.mock import Mock

import pytest

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
    service.measurement_service.measurement_exists.return_value = False

    service.extract_all = Mock(return_value=[
        {"site_id": "SITE001", "reading": 1},
        {"site_id": "SITE001", "reading": 2}
    ])
    measurements = {
        1: Mock(site_id="SITE001", measurement_date=1),
        2: Mock(site_id="SITE001", measurement_date=2),
    }
    service.transform = Mock(side_effect=lambda site_id, reading: measurements[reading["reading"]])
    service.load = Mock()

    service.run()

    assert service.transform.call_count == 2
    assert service.load.call_count == 2
    service.load.assert_any_call(measurements[1])
    service.load.assert_any_call(measurements[2])

def test_run_does_nothing_when_no_readings():
    service = make_service_with_mock()
    service.extract_all = Mock(return_value=[])
    service.transform = Mock()
    service.load = Mock()

    service.run()

    service.transform.assert_not_called()
    service.load.assert_not_called()

def test_run_skips_reading_without_site_id():
    service = make_service_with_mock()
    service.db = Mock()
    service.extract_all = Mock(return_value=[{"reading": 1}])
    service.transform = Mock()
    service.load = Mock()

    service.run()

    service.transform.assert_not_called()
    service.load.assert_not_called()

def test_run_skips_reading_when_site_not_in_db():
    service = make_service_with_mock()
    service.db = Mock()
    service.db.query().filter().scalar.return_value = None
    service.extract_all = Mock(return_value=[{"site_id": "UNKNOWN", "reading": 1}])
    service.transform = Mock()
    service.load = Mock()

    service.run()

    service.transform.assert_not_called()
    service.load.assert_not_called()

def test_run_skips_load_when_measurement_already_exists():
    service = make_service_with_mock()
    service.db = Mock()
    service.db.query().filter().scalar.return_value = "SITE001"
    service.measurement_service.measurement_exists.return_value = True
    service.extract_all = Mock(return_value=[{"site_id": "SITE001", "reading": 1}])
    service.transform = Mock(return_value=Mock(site_id="SITE001", measurement_date=1))
    service.load = Mock()

    service.run()

    service.load.assert_not_called()

def test_run_rolls_back_when_processing_raises():
    service = make_service_with_mock()
    service.db = Mock()
    service.db.query().filter().scalar.return_value = "SITE001"
    service.extract_all = Mock(return_value=[{"site_id": "SITE001", "reading": 1}])
    service.transform = Mock(side_effect=ValueError("boom"))
    service.load = Mock()

    service.run()

    service.db.rollback.assert_called_once()
    service.load.assert_not_called()

def test_extract_all_reads_and_flattens_blobs(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "container")
    service = make_service_with_mock()

    folder = Mock()
    folder.name = "brute_data/"
    blob = Mock()
    blob.name = "brute_data/file1.json"

    container_client = Mock()
    container_client.list_blobs.return_value = [folder, blob]
    blob_client = Mock()
    blob_client.download_blob().readall.return_value = json.dumps(
        [{"site_id": "SITE001"}, {"site_id": "SITE002"}]
    )
    container_client.get_blob_client.return_value = blob_client

    service.blob_service_client = Mock()
    service.blob_service_client.get_container_client.return_value = container_client

    readings = service.extract_all()

    assert readings == [{"site_id": "SITE001"}, {"site_id": "SITE002"}]
    container_client.get_blob_client.assert_called_once_with("brute_data/file1.json")

def test_extract_all_applies_limit(monkeypatch):
    monkeypatch.setenv("AZURE_STORAGE_CONTAINER_NAME", "container")
    service = make_service_with_mock()

    blobs = []
    for i in range(3):
        b = Mock()
        b.name = f"brute_data/file{i}.json"
        blobs.append(b)

    container_client = Mock()
    container_client.list_blobs.return_value = blobs
    blob_client = Mock()
    blob_client.download_blob().readall.return_value = json.dumps({"site_id": "SITE001"})
    container_client.get_blob_client.return_value = blob_client

    service.blob_service_client = Mock()
    service.blob_service_client.get_container_client.return_value = container_client

    readings = service.extract_all(limit=1)

    assert readings == [{"site_id": "SITE001"}]
    container_client.get_blob_client.assert_called_once_with("brute_data/file2.json")

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