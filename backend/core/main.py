import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from core.api.controller.alert import router as alert_router
from core.api.controller.health import router as health_router
from core.api.controller.me import router as me_router
from core.api.controller.measurement import router as measurement_router
from core.api.controller.recommendation import router as recommendation_router
from core.api.controller.prediction import router as prediction_router
from core.api.controller.site import router as site_router
from core.api.routes import router as auth_router

app = FastAPI(
    title="EnerVision API",
    description="API EnerVision — supervision de la consommation énergétique des sites.",
    version="1.0.0",
)

_DEFAULT_CORS_ORIGINS = "http://localhost:8501,http://127.0.0.1:8501"
cors_allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(site_router)
app.include_router(measurement_router)
app.include_router(alert_router)
app.include_router(prediction_router)
app.include_router(auth_router)
app.include_router(me_router)
app.include_router(recommendation_router)

# Métriques Prometheus (requêtes, latence, codes de statut par endpoint),
# exposées sur /metrics — cf. EN-280.
Instrumentator().instrument(app).expose(app)
