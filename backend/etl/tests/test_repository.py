from backend.etl.repository import get_current_reading
from backend.etl.schemas import EnergyReading


def test_get_current_reading_returns_matching_reading():
    reading = get_current_reading("SITE001")

    assert isinstance(reading, EnergyReading)
    assert reading.site_id == "SITE001"
    assert reading.data_quality == "good"


def test_get_current_reading_keeps_null_fields_for_degraded_quality():
    reading = get_current_reading("SITE002")

    assert reading.data_quality == "partial"
    assert reading.temperature_celsius is None
    assert reading.null_reasons == ["temperature_sensor_failure"]


def test_get_current_reading_keeps_all_null_fields_for_critical_quality():
    reading = get_current_reading("SITE003")

    assert reading.data_quality == "critical"
    assert reading.consumption_kw is None
    assert reading.null_reasons == ["network_loss"]


def test_get_current_reading_returns_none_when_unknown():
    assert get_current_reading("UNKNOWN") is None
