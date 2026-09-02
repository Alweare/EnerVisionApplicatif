from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from backend.etl.repository import get_current_reading, get_history
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


@router.get(
    "/{site_id}/history",
    response_model=list[EnergyReading],
    summary="Historique paginé des lectures d'un site",
)
async def get_site_history(
    site_id: str,
    start_time: datetime | None = Query(
        default=None, description="Début de la période (ISO 8601), défaut : il y a 24h"
    ),
    end_time: datetime | None = Query(
        default=None, description="Fin de la période (ISO 8601), défaut : maintenant"
    ),
    limit: int = Query(default=100, ge=1, le=1000, description="Nombre de résultats (1-1000)"),
) -> list[EnergyReading]:
    now = datetime.now()
    start = (start_time or now - timedelta(hours=24)).replace(tzinfo=None)
    end = (end_time or now).replace(tzinfo=None)

    if start > end:
        raise HTTPException(
            status_code=422, detail="start_time doit être antérieur à end_time"
        )

    readings = get_history(site_id, start, end, limit)
    if readings is None:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' introuvable")
    return readings
