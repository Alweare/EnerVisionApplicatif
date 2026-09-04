from fastapi import APIRouter, FastAPI
#testez
router = APIRouter()

@router.get(
    "/health",
    tags=["Monitoring"],
    summary="Vérifie l'état de l'API",
    description="Endpoint de health check, utilisé par Docker pour vérifier que le service répond.",
)
async def health():
    return {"status": "tests"}