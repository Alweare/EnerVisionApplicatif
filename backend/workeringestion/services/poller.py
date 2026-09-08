import asyncio
import logging
import os

from workeringestion.api import blob_storage, mock_api

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))


async def poll_once(site_id: str) -> None:
    response = await mock_api.get_current_reading_raw(site_id)

    if response.status_code == 404:
        logger.warning("Site '%s' introuvable lors du polling", site_id)
        return
    response.raise_for_status()

    blob_name = await blob_storage.archive_raw(response.text)

    data_quality = response.json().get("data_quality")
    logger.info(
        "Lecture archivée pour %s (data_quality=%s) -> %s",
        site_id,
        data_quality,
        blob_name,
    )


async def poll_alerts_once() -> None:
    response = await mock_api.get_alerts_raw()
    response.raise_for_status()

    blob_name = await blob_storage.archive_alerts_raw(response.text)

    alerts = response.json()
    logger.info("%d alerte(s) archivée(s) -> %s", len(alerts), blob_name)


async def poll_all_sites() -> None:
    site_ids = await mock_api.list_site_ids()
    for site_id in site_ids:
        try:
            await poll_once(site_id)
        except Exception:
            logger.exception("Erreur pendant le polling de %s", site_id)


async def poll_loop() -> None:
    while True:
        try:
            await poll_all_sites()
        except Exception:
            logger.exception("Erreur pendant le cycle de polling")

        try:
            await poll_alerts_once()
        except Exception:
            logger.exception("Erreur pendant le polling des alertes")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
