import asyncio
import logging

from workerIngestion.api import blob_storage, mock_api
from workerIngestion.services.poller import poll_loop

# Aucun serveur ici (pas de uvicorn) : sans ceci, les logs du polling
# n'apparaîtraient nulle part, y compris dans `docker compose logs`.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


async def main() -> None:
    try:
        await poll_loop()
    finally:
        await mock_api._client.aclose()
        await blob_storage._container_client.close()


if __name__ == "__main__":
    asyncio.run(main())
