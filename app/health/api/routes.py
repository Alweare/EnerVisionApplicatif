from fastapi import APIRouter, FastAPI

router = APIRouter()

@router.get("/health", tags=["Monitoring"],
         summary="Vérifie l'état de l'API")
async def health():
    return {"status": "test"}