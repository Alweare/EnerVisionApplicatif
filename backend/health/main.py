from fastapi import FastAPI

from backend.health.api.routes import router as health_router

app = FastAPI(
    title="EnerVision — Health",
    description="Health check du service, utilisé par Docker/Kubernetes.",
    version="1.0.0",
)

app.include_router(health_router)
