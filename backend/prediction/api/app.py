import logging
import os

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

app = FastAPI(
    title="EnerVision Prediction API",
    description="API EnerVision — prédiction de consommation énergétique (MLOps).",
    version="1.0.0",
)

app.include_router(health_router)
app.include_router(prediction_router)

Instrumentator().instrument(app)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    refresh_ml_metrics()
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
