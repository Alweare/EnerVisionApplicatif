import pytest

from backend.workerIngestion import service


async def test_get_site_returns_site(mock_httpx):
    site = await service.get_site("SITE002")

    assert site.site_id == "SITE002"


async def test_get_site_raises_when_unknown(mock_httpx):
    with pytest.raises(service.SiteNotFoundError):
        await service.get_site("UNKNOWN")


async def test_get_current_reading_raises_when_unknown(mock_httpx):
    with pytest.raises(service.SiteNotFoundError):
        await service.get_current_reading("UNKNOWN")


async def test_get_readings_raises_when_site_unknown(mock_httpx):
    with pytest.raises(service.SiteNotFoundError):
        await service.get_readings("UNKNOWN", None, None, limit=100)


async def test_get_readings_returns_list_for_known_site(mock_httpx):
    readings = await service.get_readings("SITE001", None, None, limit=100)

    assert len(readings) == 1
    assert readings[0].site_id == "SITE001"


async def test_get_alerts_passes_filters_through_to_repository(mock_httpx):
    assert len(await service.get_alerts(site_id="SITE002")) == 1
    assert len(await service.get_alerts(severity="critical")) == 1
    assert len(await service.get_alerts()) == 2


async def test_get_sensors_status_returns_repository_data(mock_httpx):
    assert set((await service.get_sensors_status()).keys()) == {"SITE001", "SITE003"}


async def test_get_stats_summary_adds_has_incomplete_data_flag(mock_httpx):
    summary = await service.get_stats_summary()

    # SITE003 est "critical" dans la fixture -> le flag doit être levé, alors
    # que la réponse brute de la Mock API n'expose pas ce champ du tout.
    assert summary.has_incomplete_data is True
    assert summary.total_sites == 3
    assert summary.total_consumption_kw == 629.44


async def test_get_stats_summary_preserves_totals_computed_by_mock_api(mock_httpx):
    summary = await service.get_stats_summary()
    by_id = {site.site_id: site for site in summary.sites}

    # On fait confiance aux totaux déjà calculés par la Mock API (exclusion
    # des null déjà faite côté serveur) : pas de recalcul de notre côté.
    assert by_id["SITE003"].current_consumption_kw is None
    assert by_id["SITE003"].load_percent is None
    assert by_id["SITE001"].load_percent == 43.7


async def test_simulate_spike_returns_result_for_known_site(mock_httpx):
    result = await service.simulate_spike("SITE002", duration_minutes=60)

    assert result.site_id == "SITE002"
    assert result.duration_minutes == 60


async def test_simulate_spike_raises_when_site_unknown(mock_httpx):
    with pytest.raises(service.SiteNotFoundError):
        await service.simulate_spike("UNKNOWN", duration_minutes=30)
