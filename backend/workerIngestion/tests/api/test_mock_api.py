from workerIngestion.api import mock_api


async def test_get_current_reading_raw_returns_matching_reading(mock_httpx):
    response = await mock_api.get_current_reading_raw("SITE001")

    assert response.status_code == 200
    assert response.json()["data_quality"] == "good"


async def test_get_current_reading_raw_keeps_null_fields_for_partial_quality(mock_httpx):
    response = await mock_api.get_current_reading_raw("SITE002")

    body = response.json()
    assert body["data_quality"] == "partial"
    assert body["temperature_celsius"] is None
    assert body["null_reasons"] == ["temperature_sensor_failure"]


async def test_get_current_reading_raw_keeps_all_null_fields_for_critical_quality(mock_httpx):
    response = await mock_api.get_current_reading_raw("SITE003")

    body = response.json()
    assert body["data_quality"] == "critical"
    assert body["consumption_kw"] is None
    assert body["null_reasons"] == ["network_loss"]


async def test_get_current_reading_raw_does_not_normalize_404(mock_httpx):
    response = await mock_api.get_current_reading_raw("UNKNOWN")

    assert response.status_code == 404


async def test_list_site_ids_returns_known_sites(mock_httpx):
    site_ids = await mock_api.list_site_ids()

    assert site_ids == ["SITE001", "SITE002", "SITE003"]
