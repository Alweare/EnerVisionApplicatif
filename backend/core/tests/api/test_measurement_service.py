from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from core.api.schemas import MeasurementRead
from core.api.service.measurement_service import (
    MeasurementNotFoundError,
    MeasurementService,
    SiteNotFoundError,
)


@pytest.fixture
def measurement_service():
    service = MeasurementService.__new__(MeasurementService)
    service.repository = Mock()
    service.site_repository = Mock()
    return service


def _measurement(site_id: str = "SITE001") -> MeasurementRead:
    return MeasurementRead(
        measurement_id=uuid4(),
        site_id=site_id,
        measurement_date=datetime(2026, 9, 4, 9, 0, 0),
        consumption_kw=104.47,
        consumption_kwh=104.47,
        voltage_v=402.6,
        current_a=163.9,
        power_factor=0.914,
        temperature_celsius=None,
        humidity_percent=61.0,
        null_reason=["temperature_sensor_failure"],
        data_quality="partial",
        created_at=datetime(2026, 9, 4, 9, 9, 1),
    )


# --- get_current_measurement -------------------------------------------------

def test_get_current_measurement_raises_when_site_unknown(measurement_service):
    measurement_service.site_repository.exists.return_value = False

    with pytest.raises(SiteNotFoundError) as error:
        measurement_service.get_current_measurement("SITE999")

    assert error.value.site_id == "SITE999"
    measurement_service.repository.get_last_by_site.assert_not_called()


def test_get_current_measurement_raises_when_no_measurement(measurement_service):
    measurement_service.site_repository.exists.return_value = True
    measurement_service.repository.get_last_by_site.return_value = None

    with pytest.raises(MeasurementNotFoundError):
        measurement_service.get_current_measurement("SITE001")


def test_get_current_measurement_returns_last_measurement(measurement_service):
    expected = _measurement()
    measurement_service.site_repository.exists.return_value = True
    measurement_service.repository.get_last_by_site.return_value = expected

    result = measurement_service.get_current_measurement("SITE001")

    assert result is expected
    assert isinstance(result, MeasurementRead)
    measurement_service.repository.get_last_by_site.assert_called_once_with("SITE001")


# --- list_measurements -----------------------------------------------------

def test_list_measurements_raises_when_site_unknown(measurement_service):
    measurement_service.site_repository.exists.return_value = False

    with pytest.raises(SiteNotFoundError):
        measurement_service.list_measurements("SITE999", limit=100, offset=0)

    measurement_service.repository.list_by_site.assert_not_called()


def test_list_measurements_passes_pagination_to_repository(measurement_service):
    rows = [_measurement(), _measurement()]
    measurement_service.site_repository.exists.return_value = True
    measurement_service.repository.list_by_site.return_value = rows

    result = measurement_service.list_measurements("SITE001", limit=50, offset=10)

    assert result == rows
    measurement_service.repository.list_by_site.assert_called_once_with(
        "SITE001", limit=50, offset=10
    )


def test_list_measurements_returns_empty_list_when_no_row(measurement_service):
    measurement_service.site_repository.exists.return_value = True
    measurement_service.repository.list_by_site.return_value = []

    assert measurement_service.list_measurements("SITE001", limit=100, offset=0) == []
