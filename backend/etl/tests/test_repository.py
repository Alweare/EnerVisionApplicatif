from datetime import datetime, timedelta

from backend.etl.repository import (
    get_alerts,
    get_current_reading,
    get_history,
    get_sensors_status,
    get_stats_summary,
)
from backend.etl.schemas import Alert, EnergyReading, SiteSensorsStatus


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


def test_get_history_returns_none_for_unknown_site():
    start = datetime.fromisoformat("2024-06-01T00:00:00")
    end = datetime.fromisoformat("2024-06-01T05:00:00")

    assert get_history("UNKNOWN", start, end, limit=100) is None


def test_get_history_returns_hourly_readings_sorted_ascending():
    start = datetime.fromisoformat("2024-06-01T00:00:00")
    end = datetime.fromisoformat("2024-06-01T05:00:00")

    readings = get_history("SITE001", start, end, limit=100)

    assert readings is not None
    assert len(readings) == 6
    timestamps = [reading.timestamp for reading in readings]
    assert timestamps == sorted(timestamps)
    assert timestamps[0] == start
    assert timestamps[-1] == end


def test_get_history_respects_limit_and_keeps_most_recent():
    start = datetime.fromisoformat("2024-06-01T00:00:00")
    end = datetime.fromisoformat("2024-06-01T09:00:00")  # 10 lectures possibles

    readings = get_history("SITE001", start, end, limit=3)

    assert readings is not None
    assert len(readings) == 3
    timestamps = [reading.timestamp for reading in readings]
    assert timestamps == sorted(timestamps)
    assert timestamps[-1] == end
    assert timestamps[0] == end - timedelta(hours=2)


def test_get_sensors_status_returns_all_known_sites():
    status = get_sensors_status()

    assert set(status.keys()) == {"SITE001", "SITE002", "SITE003"}
    assert all(isinstance(value, SiteSensorsStatus) for value in status.values())


def test_get_sensors_status_overall_ok_when_all_sensors_ok():
    status = get_sensors_status()["SITE001"]
    sensors = [
        status.sensors.consumption,
        status.sensors.electrical,
        status.sensors.temperature,
        status.sensors.humidity,
        status.sensors.network,
    ]

    assert status.overall == "ok"
    assert all(sensor.status == "ok" and sensor.failing_until is None for sensor in sensors)


def test_get_alerts_returns_all_alerts_without_filters():
    alerts = get_alerts()

    assert len(alerts) == 4
    assert all(isinstance(alert, Alert) for alert in alerts)


def test_get_alerts_filters_by_site_id():
    alerts = get_alerts(site_id="SITE002")

    assert len(alerts) == 2
    assert all(alert.site_id == "SITE002" for alert in alerts)


def test_get_alerts_filters_by_severity():
    alerts = get_alerts(severity="critical")

    assert len(alerts) == 1
    assert alerts[0].alert_id == "ALR-SITE002-1718458320"


def test_get_alerts_combines_site_id_and_severity_filters():
    assert get_alerts(site_id="SITE002", severity="critical") != []
    assert get_alerts(site_id="SITE002", severity="low") == []


def test_get_alerts_returns_empty_list_when_no_alert_matches():
    assert get_alerts(site_id="UNKNOWN") == []


def test_get_sensors_status_degraded_reflects_failing_sensor():
    status = get_sensors_status()["SITE002"]

    assert status.overall == "degraded"
    assert status.sensors.temperature.status == "failing"
    assert status.sensors.temperature.failing_until is not None
    assert status.sensors.network.status == "ok"


def test_get_sensors_status_critical_reflects_network_loss():
    status = get_sensors_status()["SITE003"]

    assert status.overall == "critical"
    assert status.sensors.network.status == "failing"


def test_get_stats_summary_excludes_null_consumption_sites_from_total():
    summary = get_stats_summary()

    # SITE003 est "critical" (consumption_kw=None) : exclu du total, mais
    # comptabilisé dans total_sites/total_capacity_kw.
    assert summary.total_sites == 3
    assert summary.total_capacity_kw == 2000
    assert summary.total_consumption_kw == 629.44


def test_get_stats_summary_average_load_percent_is_ratio_of_totals():
    summary = get_stats_summary()

    assert summary.average_load_percent == 31.5


def test_get_stats_summary_flags_incomplete_data_when_a_site_is_critical():
    summary = get_stats_summary()

    assert summary.has_incomplete_data is True


def test_get_stats_summary_per_site_load_percent_and_null_handling():
    summary = get_stats_summary()
    by_id = {site.site_id: site for site in summary.sites}

    assert by_id["SITE001"].load_percent == 43.7
    assert by_id["SITE003"].current_consumption_kw is None
    assert by_id["SITE003"].load_percent is None
    assert by_id["SITE003"].data_quality == "critical"
