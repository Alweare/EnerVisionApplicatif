from fastapi import FastAPI

from core.api.controller.measurement import router as measurement_router
from core.api.controller.site import router as site_router

app = FastAPI(
    title="EnerVision API",
    description="API EnerVision — supervision de la consommation énergétique des sites.",
    version="1.0.0",
)

#Déclarer les routes ici, dans chaque module faire un routes.py sur le modèle de health
app.include_router(site_router)
app.include_router(measurement_router)
