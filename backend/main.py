from fastapi import FastAPI

from backend.health.api.routes import router as health_router
from backend.sites.api.routes import router as sites_router

app = FastAPI(
    title="EnerVision API",
    version="1.0.0"
)

#Déclarer les routes ici, dans chaque module faire un routes.py sur le modèle de health
app.include_router(health_router)
app.include_router(sites_router)