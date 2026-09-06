from datetime import datetime
from unittest.mock import Mock

import pytest

from etl.service.measurement_service import MeasurementService


@pytest.fixture
def measurement_service():
    service = MeasurementService.__new__(MeasurementService)
    service.repository = Mock()
    return service


@pytest.fixture
def cleaned_reading():
    return {
        "timestamp": datetime(2026, 9, 2, 14, 32, 0),
        "consumption_kw": 87.34,
        "consumption_kwh": 87.34,
        "voltage_v": 401.2,
        "current_a": 132.5,
        "power_factor": 0.923,
        "temperature_celsius": 22.1,
        "humidity_percent": 58.4,
        "null_reasons": [],
        "data_quality": "good",
    }


def test_build_measurement_maps_every_field(measurement_service, cleaned_reading):
    measurement = measurement_service.build_measurement("SITE_TEST", cleaned_reading)

    assert measurement.site_id == "SITE_TEST"
    assert measurement.measurement_date == cleaned_reading["timestamp"]
    assert measurement.consumption_kw == 87.34
    assert measurement.consumption_kwh == 87.34
    assert measurement.voltage_v == 401.2
    assert measurement.current_a == 132.5
    assert measurement.power_factor == 0.923
    assert measurement.temperature_celsius == 22.1
    assert measurement.humidity_percent == 58.4
    assert measurement.null_reason == []
    assert measurement.data_quality == "good"


def test_build_measurement_does_not_touch_the_database(measurement_service, cleaned_reading):
    measurement_service.build_measurement("SITE_TEST", cleaned_reading)

    measurement_service.repository.add.assert_not_called()


def test_add_measurement_delegates_to_repository(measurement_service, cleaned_reading):
    measurement = measurement_service.build_measurement("SITE_TEST", cleaned_reading)

    measurement_service.add_measurement(measurement)

    measurement_service.repository.add.assert_called_once_with(measurement)
    added = measurement_service.repository.add.call_args[0][0]
    assert added.consumption_kw == 87.34


def test_get_last_measurement_delegates_to_repository(measurement_service):
    expected = Mock()
    measurement_service.repository.get_last_measurement.return_value = expected

    assert measurement_service.get_last_measurement("SITE001") is expected
    measurement_service.repository.get_last_measurement.assert_called_once_with("SITE001")
