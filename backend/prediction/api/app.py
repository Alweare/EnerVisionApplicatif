import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from prediction.api.controller.health import router as health_router
from prediction.api.controller.prediction import router as prediction_router
from prediction.observability.ml_metrics import refresh_ml_metrics
from prediction.scheduler.scheduler import create_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Jamais démarré au simple import de ce module : create_scheduler() n'est
    # appelée qu'ici, à l'exécution réelle du lifespan (pas quand un test
    # importe `app`, cf. tests/conftest.py::PREDICTION_SCHEDULER_ENABLED).
    scheduler = create_scheduler()
    if scheduler is not None:
        scheduler.start()
        logger.info("scheduler started", extra={"event": "scheduler_started"})

    app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
            logger.info("scheduler stopped", extra={"event": "scheduler_stopped"})


app = FastAPI(
    title="EnerVision Prediction API",
    description="API EnerVision — prédiction de consommation énergétique (MLOps).",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(prediction_router)

Instrumentator().instrument(app)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    refresh_ml_metrics()
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
