from fastapi import APIRouter, HTTPException

from backend.etl.repository import get_current_reading
from backend.etl.schemas import EnergyReading

router = APIRouter(prefix="/api/v1/sites", tags=["ETL"])


@router.get(
    "/{site_id}/current",
    response_model=EnergyReading,
    summary="Dernière lecture connue d'un site",
)
async def get_site_current_reading(site_id: str) -> EnergyReading:
    reading = get_current_reading(site_id)
    if reading is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' introuvable")
    return reading
