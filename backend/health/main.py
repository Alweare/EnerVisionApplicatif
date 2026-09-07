from fastapi import FastAPI

from health.api.routes import router as health_router

app = FastAPI(
    title="EnerVision — Health",
    description="Endpoint de health check, utilisé par Docker et le pipeline CI/CD (DAST).",
    version="1.0.0",
)

app.include_router(health_router)
