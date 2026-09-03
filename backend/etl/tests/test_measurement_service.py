from datetime import datetime
from unittest.mock import Mock

import pytest

from etl.service.measurement_service import MeasurementService

@pytest.fixture
def measurement_service():
    service = MeasurementService.__new__(MeasurementService)
    service.repository = Mock()
    return service

def test_save_measurement_calls_repository_correctly():
    mock_repository = Mock()
    service = MeasurementService.__new__(MeasurementService)
    service.repository = mock_repository

    cleaned = {
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

    measurement = service.build_measurement("SITE_TEST", cleaned)
    service.save_measurement(measurement)

    mock_repository.save.assert_called_once()
    saved_measurement = mock_repository.save.call_args[0][0]
    assert saved_measurement.consumption_kw == 87.34