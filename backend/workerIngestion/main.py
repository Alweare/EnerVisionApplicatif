import asyncio
import logging

from workerIngestion import blob_archive, repository
from workerIngestion.poller import poll_loop

# Aucun serveur ici pour configurer un handler (pas de uvicorn) : sans ceci,
# les logs du polling n'apparaîtraient nulle part, y compris dans
# `docker compose logs`.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


async def main() -> None:
    try:
        await poll_loop()
    finally:
        await repository._client.aclose()
        await blob_archive._container_client.close()


if __name__ == "__main__":
    asyncio.run(main())
