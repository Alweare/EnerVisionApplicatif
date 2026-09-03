from fastapi import FastAPI

from backend.workerIngestion.api.routes import sites_router

app = FastAPI(
    title="EnerVision — Worker Ingestion",
    description=(
        "Proxy fidèle de la Mock API IoT (cf. EADL - 04) — dernière lecture "
        "connue d'un site. Utilisé pour le polling vers la Mock API et, à "
        "terme, l'écriture des lots bruts sur Azure Blob."
    ),
    version="1.0.0",
)

app.include_router(sites_router)
