import json
import logging

from workerIngestion.services import poller


async def test_poll_once_archives_raw_json_before_any_parsing(mock_httpx, mock_blob):
    await poller.poll_once("SITE001")

    assert len(mock_blob) == 1
    upload = mock_blob[0]
    assert upload["name"].startswith("brute_data/")
    assert upload["overwrite"] is False
    archived = json.loads(upload["data"])
    assert archived["site_id"] == "SITE001"
    assert archived["data_quality"] == "good"


async def test_poll_once_preserves_null_fields_in_the_archived_payload(mock_httpx, mock_blob):
    # SITE003 est "critical" dans la fixture : tous les champs de mesure sont
    # null. C'est exactement ce que le ticket demande de ne jamais perdre.
    await poller.poll_once("SITE003")

    archived = json.loads(mock_blob[0]["data"])
    assert archived["data_quality"] == "critical"
    assert archived["consumption_kw"] is None
    assert archived["null_reasons"] == ["network_loss"]


async def test_poll_once_logs_the_reading_for_a_known_site(mock_httpx, mock_blob, caplog):
    with caplog.at_level(logging.INFO, logger="workerIngestion.services.poller"):
        await poller.poll_once("SITE001")

    assert any("SITE001" in record.message for record in caplog.records)


async def test_poll_once_does_not_archive_when_site_unknown(mock_httpx, mock_blob):
    await poller.poll_once("UNKNOWN")

    assert mock_blob == []


async def test_poll_once_logs_a_warning_and_does_not_raise_when_site_unknown(
    mock_httpx, mock_blob, caplog
):
    with caplog.at_level(logging.WARNING, logger="workerIngestion.services.poller"):
        await poller.poll_once("UNKNOWN")

    assert any(
        record.levelname == "WARNING" and "UNKNOWN" in record.message
        for record in caplog.records
    )


async def test_poll_all_sites_polls_every_known_site(mock_httpx, mock_blob):
    await poller.poll_all_sites()

    archived_sites = {json.loads(u["data"])["site_id"] for u in mock_blob}
    assert archived_sites == {"SITE001", "SITE002", "SITE003"}
    assert len(mock_blob) == 3


async def test_poll_all_sites_continues_when_one_site_fails(mock_httpx, mock_blob, monkeypatch):
    async def failing_poll_once(site_id):
        if site_id == "SITE002":
            raise RuntimeError("boom")
        return await real_poll_once(site_id)

    real_poll_once = poller.poll_once
    monkeypatch.setattr(poller, "poll_once", failing_poll_once)

    await poller.poll_all_sites()

    archived_sites = {json.loads(u["data"])["site_id"] for u in mock_blob}
    assert archived_sites == {"SITE001", "SITE003"}  # SITE002 a échoué, les autres continuent
