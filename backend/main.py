import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.api.controller.measurement import router as measurement_router
from core.api.controller.site import router as site_router
from core.api.routes import router as core_router
from health.api.routes import router as health_router

app = FastAPI(
    title="EnerVision API",
    description="API EnerVision — supervision de la consommation énergétique des sites.",
    version="1.0.0",
)

# Origines autorisées pour les appels navigateur (dashboard Streamlit, cf. EN-171).
# Surchargeable via CORS_ALLOWED_ORIGINS (liste séparée par des virgules).
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

#Déclarer les routes ici, dans chaque module faire un routes.py sur le modèle de health
app.include_router(health_router)
app.include_router(site_router)
app.include_router(measurement_router)
app.include_router(core_router)
