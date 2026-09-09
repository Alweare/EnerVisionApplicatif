from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["Monitoring"])
async def health() -> dict:
    return {"status": "ok"}
