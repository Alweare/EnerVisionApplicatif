from datetime import datetime
from unittest.mock import Mock

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