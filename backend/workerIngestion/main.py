from fastapi import FastAPI

from backend.workerIngestion.api.routes import (
    alerts_router,
    readings_router,
    sensors_router,
    simulate_router,
    sites_router,
    stats_router,
)

app = FastAPI(
    title="EnerVision — Worker Ingestion",
    description=(
        "Proxy fidèle de la Mock API IoT (cf. EADL - 04) — sites, lectures, "
        "capteurs, alertes, agrégats et simulation de pics. Utilisé pour le "
        "polling vers la Mock API et, à terme, l'écriture des lots bruts sur "
        "Azure Blob."
    ),
    version="1.0.0",
)

app.include_router(sites_router)
app.include_router(readings_router)
app.include_router(sensors_router)
app.include_router(alerts_router)
app.include_router(stats_router)
app.include_router(simulate_router)
