import httpx
import pytest

from backend.workerIngestion import repository
from backend.workerIngestion.schemas import Alert, EnergyReading, Site, SiteSensorsStatus


async def test_list_sites_parses_real_shape(mock_httpx):
    sites = await repository.list_sites()

    assert len(sites) == 3
    assert all(isinstance(site, Site) for site in sites)
    assert sites[0].capacity_kw == 200.0  # float, pas int


async def test_get_site_returns_matching_site(mock_httpx):
    site = await repository.get_site("SITE002")

    assert site is not None
    assert site.site_id == "SITE002"


async def test_get_site_returns_none_when_unknown(mock_httpx):
    assert await repository.get_site("UNKNOWN") is None


async def test_get_current_reading_returns_matching_reading(mock_httpx):
    reading = await repository.get_current_reading("SITE001")

    assert isinstance(reading, EnergyReading)
    assert reading.data_quality == "good"


async def test_get_current_reading_keeps_null_fields_for_critical_quality(mock_httpx):
    reading = await repository.get_current_reading("SITE003")

    assert reading.data_quality == "critical"
    assert reading.consumption_kw is None
    assert reading.null_reasons == ["network_loss"]


async def test_get_current_reading_returns_none_when_unknown(mock_httpx):
    assert await repository.get_current_reading("UNKNOWN") is None


async def test_get_readings_returns_none_when_site_unknown(mock_httpx):
    assert await repository.get_readings("UNKNOWN", None, None, limit=100) is None


async def test_get_readings_returns_list_for_known_site(mock_httpx):
    readings = await repository.get_readings("SITE002", None, None, limit=100)

    assert readings is not None
    assert all(isinstance(r, EnergyReading) for r in readings)
    assert readings[0].site_id == "SITE002"


async def test_get_readings_without_site_id_does_not_swallow_a_404(monkeypatch):
    # Régression : un 404 sans site_id ne doit pas être interprété comme
    # "site introuvable" (il n'y a pas de site à ne pas trouver) — il doit
    # remonter comme une vraie erreur HTTP, pas disparaître en `None`.
    async def always_404(url, params=None):
        request = httpx.Request("GET", "http://mock-api.test")
        return httpx.Response(404, json={"detail": "boom"}, request=request)

    monkeypatch.setattr(repository._client, "get", always_404)

    with pytest.raises(httpx.HTTPStatusError):
        await repository.get_readings(None, None, None, limit=100)


async def test_get_sensors_status_parses_dict_keyed_by_site(mock_httpx):
    status = await repository.get_sensors_status()

    assert set(status.keys()) == {"SITE001", "SITE003"}
    assert all(isinstance(value, SiteSensorsStatus) for value in status.values())
    assert status["SITE003"].overall == "critical"


async def test_list_alerts_without_filters_returns_all(mock_httpx):
    alerts = await repository.list_alerts(None, None)

    assert len(alerts) == 2
    assert all(isinstance(alert, Alert) for alert in alerts)


async def test_list_alerts_filters_by_site_id(mock_httpx):
    alerts = await repository.list_alerts("SITE002", None)

    assert len(alerts) == 1
    assert alerts[0].site_id == "SITE002"


async def test_list_alerts_filters_by_severity(mock_httpx):
    alerts = await repository.list_alerts(None, "critical")

    assert len(alerts) == 1
    assert alerts[0].severity == "critical"


async def test_get_stats_summary_raw_returns_dict_without_has_incomplete_data(mock_httpx):
    raw = await repository.get_stats_summary_raw()

    assert raw["total_sites"] == 3
    assert "has_incomplete_data" not in raw


async def test_simulate_spike_returns_payload_for_known_site(mock_httpx):
    result = await repository.simulate_spike("SITE002", duration_minutes=60)

    assert result is not None
    assert result["site_id"] == "SITE002"
    assert result["duration_minutes"] == 60


async def test_simulate_spike_returns_none_for_unknown_site(mock_httpx):
    assert await repository.simulate_spike("UNKNOWN", duration_minutes=30) is None
