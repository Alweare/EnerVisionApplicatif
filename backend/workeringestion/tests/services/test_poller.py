import json
import logging

from azure.core.exceptions import ServiceRequestError

from workeringestion.api import blob_storage
from workeringestion.services import poller


async def test_poll_once_archives_raw_json_before_any_parsing(mock_httpx, mock_blob):
    await poller.poll_once("SITE001")

    assert len(mock_blob) == 1
    upload = mock_blob[0]
    assert upload["name"].startswith("measures/")
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
    with caplog.at_level(logging.INFO, logger="workeringestion.services.poller"):
        await poller.poll_once("SITE001")

    assert any("SITE001" in record.message for record in caplog.records)


async def test_poll_once_does_not_archive_when_site_unknown(mock_httpx, mock_blob):
    await poller.poll_once("UNKNOWN")

    assert mock_blob == []


async def test_poll_once_logs_a_warning_and_does_not_raise_when_site_unknown(
    mock_httpx, mock_blob, caplog
):
    with caplog.at_level(logging.WARNING, logger="workeringestion.services.poller"):
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


async def test_poll_alerts_once_archives_the_raw_response_under_alerts(mock_httpx, mock_blob):
    await poller.poll_alerts_once()

    assert len(mock_blob) == 1
    upload = mock_blob[0]
    assert upload["name"].startswith("alert/")
    assert upload["overwrite"] is False
    archived = json.loads(upload["data"])
    assert [alert["alert_id"] for alert in archived] == [
        "ALR-SITE002-1718458320",
        "ALR-SITE001-1718458500",
    ]


async def test_poll_alerts_once_makes_a_single_call_for_all_sites(mock_httpx, mock_blob):
    await poller.poll_alerts_once()

    assert len(mock_blob) == 1


async def test_poll_alerts_once_logs_how_many_alerts_were_archived(mock_httpx, mock_blob, caplog):
    with caplog.at_level(logging.INFO, logger="workeringestion.services.poller"):
        await poller.poll_alerts_once()

    assert any("2 alerte" in record.getMessage() for record in caplog.records)


async def test_poll_loop_archives_measurements_and_alerts_in_the_same_cycle(
    mock_httpx, mock_blob, monkeypatch
):
    async def stop_after_first_cycle(_seconds):
        raise StopAsyncIteration

    monkeypatch.setattr(poller.asyncio, "sleep", stop_after_first_cycle)

    try:
        await poller.poll_loop()
    except StopAsyncIteration:
        pass

    prefixes = [u["name"].split("/")[0] for u in mock_blob]
    assert prefixes.count("measures") == 3  
    assert prefixes.count("alert") == 1      


async def test_poll_loop_still_archives_measurements_when_alerts_fail(
    mock_httpx, mock_blob, monkeypatch, caplog
):
    async def failing_alerts():
        raise RuntimeError("alerts indisponible")

    async def stop_after_first_cycle(_seconds):
        raise StopAsyncIteration

    monkeypatch.setattr(poller, "poll_alerts_once", failing_alerts)
    monkeypatch.setattr(poller.asyncio, "sleep", stop_after_first_cycle)

    with caplog.at_level(logging.ERROR, logger="workeringestion.services.poller"):
        try:
            await poller.poll_loop()
        except StopAsyncIteration:
            pass

    assert len(mock_blob) == 3
    assert any("alertes" in record.getMessage() for record in caplog.records)


async def test_poll_all_sites_continues_when_one_upload_fails(mock_httpx, monkeypatch, caplog):
    attempts: list[str] = []
    uploads: list[str] = []

    async def flaky_upload_blob(name, data, overwrite=False):
        attempts.append(name)
        if len(attempts) == 2:
            raise ServiceRequestError("Connection refused")
        uploads.append(name)

    monkeypatch.setattr(blob_storage._container_client, "upload_blob", flaky_upload_blob)

    with caplog.at_level(logging.ERROR, logger="workeringestion.services.poller"):
        await poller.poll_all_sites()

    assert len(attempts) == 3
    assert len(uploads) == 2
    assert any("SITE002" in r.getMessage() for r in caplog.records)
