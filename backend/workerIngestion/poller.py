import asyncio
import logging
import os

from backend.workerIngestion import service

logger = logging.getLogger(__name__)

# Un seul site pour l'instant (cf. ticket) — à terme, boucler sur tous les
# sites connus (backend.sites une fois branché, ou une liste dédiée).
POLL_SITE_ID = os.environ.get("POLL_SITE_ID", "SITE001")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))


async def poll_once(site_id: str = POLL_SITE_ID) -> None:
    """Un seul cycle poll+log — le point d'insertion de l'archivage Blob à venir."""
    try:
        reading = await service.get_current_reading(site_id)
    except service.SiteNotFoundError:
        logger.warning("Site '%s' introuvable lors du polling", site_id)
        return

    # TODO(archivage Blob) : écrire le JSON brut de la réponse ici, avant
    # toute transformation, une fois le SAS token disponible.
    logger.info("Lecture récupérée pour %s : %s", site_id, reading.model_dump_json())


async def poll_loop() -> None:
    while True:
        try:
            await poll_once()
        except Exception:
            logger.exception("Erreur pendant le polling de %s", POLL_SITE_ID)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
