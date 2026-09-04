import pytest

from workeringestion import service


async def test_get_current_reading_returns_reading(mock_httpx):
    reading = await service.get_current_reading("SITE001")

    assert reading.site_id == "SITE001"


async def test_get_current_reading_raises_when_unknown(mock_httpx):
    with pytest.raises(service.SiteNotFoundError):
        await service.get_current_reading("UNKNOWN")
