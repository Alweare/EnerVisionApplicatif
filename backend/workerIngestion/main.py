import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from workerIngestion.api.routes import sites_router
from workerIngestion.poller import poll_loop

# uvicorn ne configure pas de handler pour nos loggers applicatifs (seulement
# les siens) : sans ceci, les logs du polling n'apparaîtraient nulle part,
# y compris dans `docker compose logs`.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(poll_loop())
    yield
    task.cancel()


app = FastAPI(
    title="EnerVision — Worker Ingestion",
    description=(
        "Proxy fidèle de la Mock API IoT (cf. EADL - 04) — dernière lecture "
        "connue d'un site. Poll la Mock API en tâche de fond (toutes les "
        "POLL_INTERVAL_SECONDS) et, à terme, écrit les lots bruts sur Azure Blob."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(sites_router)
