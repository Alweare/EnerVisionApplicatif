from fastapi import FastAPI

from backend.etl.api.routes import alerts_router
from backend.etl.api.routes import router as etl_router
from backend.etl.api.routes import sensors_router
from backend.etl.api.routes import stats_router
from backend.health.api.routes import router as health_router
from backend.sites.api.routes import router as sites_router

app = FastAPI(
    title="EnerVision API",
    description="API EnerVision — supervision de la consommation énergétique des sites.",
    version="1.0.0"
)

#Déclarer les routes ici, dans chaque module faire un routes.py sur le modèle de health
app.include_router(health_router)
app.include_router(sites_router)
app.include_router(etl_router)
app.include_router(sensors_router)
app.include_router(alerts_router)
app.include_router(stats_router)