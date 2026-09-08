import logging
from datetime import datetime, timezone

import pytest
from azure.core.exceptions import (
    ClientAuthenticationError,
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
    ServiceRequestError,
)

from workeringestion.api import blob_storage


async def test_archive_raw_uploads_and_returns_the_blob_name(mock_blob):
    blob_name = await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert blob_name.startswith("measures/")
    assert mock_blob[0]["name"] == blob_name
    assert mock_blob[0]["data"] == '{"site_id": "SITE001"}'


async def test_archive_raw_logs_a_warning_and_does_not_raise_on_name_collision(
    monkeypatch, caplog
):
    async def fake_upload_blob(name, data, overwrite=False):
        raise ResourceExistsError("The specified blob already exists.")

    monkeypatch.setattr(blob_storage._container_client, "upload_blob", fake_upload_blob)

    with caplog.at_level(logging.WARNING, logger="workeringestion.api.blob_storage"):
        blob_name = await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert blob_name.startswith("measures/")
    assert any(
        record.levelname == "WARNING" and "déjà existant" in record.message
        for record in caplog.records
    )


async def test_archive_raw_writes_under_the_measures_path(mock_blob):
    blob_name = await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert blob_name.startswith("measures/")


async def test_archive_alerts_raw_writes_under_the_alert_path(mock_blob):
    blob_name = await blob_storage.archive_alerts_raw('[{"alert_id": "ALR-1"}]')

    assert blob_name.startswith("alert/")
    assert mock_blob[0]["name"] == blob_name
    assert mock_blob[0]["data"] == '[{"alert_id": "ALR-1"}]'
    assert mock_blob[0]["overwrite"] is False


async def test_the_two_paths_never_overlap(mock_blob):
    measurement = await blob_storage.archive_raw('{"site_id": "SITE001"}')
    alert = await blob_storage.archive_alerts_raw('[{"alert_id": "ALR-1"}]')

    assert not alert.startswith(blob_storage.MEASURES_PREFIX)
    assert not measurement.startswith(blob_storage.ALERT_PATH)


def _upload_raising(exc):
    async def fake_upload_blob(name, data, overwrite=False):
        raise exc
    return fake_upload_blob


async def test_archive_raw_logs_and_reraises_when_the_sas_is_invalid(monkeypatch, caplog):
    monkeypatch.setattr(
        blob_storage._container_client, "upload_blob",
        _upload_raising(ClientAuthenticationError("Signature did not match.")),
    )

    with caplog.at_level(logging.ERROR, logger="workeringestion.api.blob_storage"):
        with pytest.raises(ClientAuthenticationError):
            await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert any("AZURE_SAS_INGESTION" in r.getMessage() for r in caplog.records)


async def test_archive_raw_logs_and_reraises_when_the_container_is_missing(monkeypatch, caplog):
    monkeypatch.setattr(
        blob_storage._container_client, "upload_blob",
        _upload_raising(ResourceNotFoundError("The specified container does not exist.")),
    )

    with caplog.at_level(logging.ERROR, logger="workeringestion.api.blob_storage"):
        with pytest.raises(ResourceNotFoundError):
            await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert any("introuvable" in r.getMessage() for r in caplog.records)


async def test_archive_raw_logs_and_reraises_when_azure_is_unreachable(monkeypatch, caplog):
    monkeypatch.setattr(
        blob_storage._container_client, "upload_blob",
        _upload_raising(ServiceRequestError("Connection refused")),
    )

    with caplog.at_level(logging.ERROR, logger="workeringestion.api.blob_storage"):
        with pytest.raises(ServiceRequestError):
            await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert any("injoignable" in r.getMessage() for r in caplog.records)


async def test_archive_raw_logs_and_reraises_on_any_other_azure_error(monkeypatch, caplog):
    monkeypatch.setattr(
        blob_storage._container_client, "upload_blob",
        _upload_raising(HttpResponseError("500 Internal Server Error")),
    )

    with caplog.at_level(logging.ERROR, logger="workeringestion.api.blob_storage"):
        with pytest.raises(HttpResponseError):
            await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert any("Échec d'écriture" in r.getMessage() for r in caplog.records)


async def test_archive_alerts_raw_also_propagates_upload_failures(monkeypatch):
    monkeypatch.setattr(
        blob_storage._container_client, "upload_blob",
        _upload_raising(ServiceRequestError("Connection refused")),
    )

    with pytest.raises(ServiceRequestError):
        await blob_storage.archive_alerts_raw('[{"alert_id": "ALR-1"}]')

async def test_archive_raw_puts_the_date_in_the_blob_path(mock_blob):
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")

    blob_name = await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert blob_name.startswith(f"measures/{today}/")
    assert blob_name.endswith(".json")

async def test_archive_raw_never_writes_flat_under_the_prefix(mock_blob):
    blob_name = await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert blob_name.count("/") == 4  # measures/AAAA/MM/JJ/<uuid>.json

async def test_archive_alerts_raw_puts_the_date_in_the_blob_path(mock_blob):
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")

    blob_name = await blob_storage.archive_alerts_raw('[{"alert_id": "ALR-1"}]')

    assert blob_name.startswith(f"alert/{today}/")
    assert blob_name.endswith(".json")

async def test_archive_alerts_raw_never_writes_flat_under_the_prefix(mock_blob):
    # Même raison que pour les mesures : l'ETL ne liste que les jours utiles.
    blob_name = await blob_storage.archive_alerts_raw('[{"alert_id": "ALR-1"}]')

    assert blob_name.count("/") == 4  # alert/AAAA/MM/JJ/<uuid>.json
