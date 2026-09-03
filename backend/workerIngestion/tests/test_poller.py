import logging

from backend.workerIngestion import poller


async def test_poll_once_logs_the_reading_for_a_known_site(mock_httpx, caplog):
    with caplog.at_level(logging.INFO, logger="backend.workerIngestion.poller"):
        await poller.poll_once("SITE001")

    assert any("SITE001" in record.message for record in caplog.records)


async def test_poll_once_logs_a_warning_and_does_not_raise_when_site_unknown(
    mock_httpx, caplog
):
    with caplog.at_level(logging.WARNING, logger="backend.workerIngestion.poller"):
        await poller.poll_once("UNKNOWN")

    assert any(
        record.levelname == "WARNING" and "UNKNOWN" in record.message
        for record in caplog.records
    )
