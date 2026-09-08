import asyncio
import logging

from workeringestion.api import blob_storage, mock_api
from workeringestion.services.poller import poll_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


async def main() -> None:
    try:
        await poll_loop()
    finally:
        await mock_api._client.aclose()
        await blob_storage._container_client.close()


if __name__ == "__main__":
    asyncio.run(main())
