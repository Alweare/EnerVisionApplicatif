import asyncio
import logging
import os
import time

from shared import heartbeat
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
        extra={"event": "worker.lecture_archivee", "site_id": site_id,
               "data_quality": data_quality, "blob": blob_name},
    )


async def poll_alerts_once() -> None:
    response = await mock_api.get_alerts_raw()
    response.raise_for_status()

    blob_name = await blob_storage.archive_alerts_raw(response.text)

    alerts = response.json()
    logger.info(
        "%d alerte(s) archivée(s) -> %s", len(alerts), blob_name,
        extra={"event": "worker.alertes_archivees", "alertes": len(alerts),
               "blob": blob_name},
    )


async def poll_all_sites() -> None:
    site_ids = await mock_api.list_site_ids()
    for site_id in site_ids:
        try:
            await poll_once(site_id)
        except Exception:
            logger.exception("Erreur pendant le polling de %s", site_id)


async def poll_loop() -> None:
    while True:
        debut = time.perf_counter()
        mesures_ok = alertes_ok = True

        try:
            await poll_all_sites()
        except Exception:
            mesures_ok = False
            logger.exception(
                "Erreur pendant le cycle de polling",
                extra={"event": "worker.cycle_echec", "phase": "mesures"},
            )

        try:
            await poll_alerts_once()
        except Exception:
            alertes_ok = False
            logger.exception(
                "Erreur pendant le polling des alertes",
                extra={"event": "worker.cycle_echec", "phase": "alertes"},
            )

        # Battement de cœur : voir le commentaire équivalent côté ETL. Un
        # fichier pour le healthcheck Docker, un log pour l'alerte Grafana.
        heartbeat.touch()
        logger.info(
            "Cycle de polling terminé",
            extra={
                "event": "worker.heartbeat",
                "mesures_ok": mesures_ok,
                "alertes_ok": alertes_ok,
                "duration_ms": round((time.perf_counter() - debut) * 1000, 1),
            },
        )

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
