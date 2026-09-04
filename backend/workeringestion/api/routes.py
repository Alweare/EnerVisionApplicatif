from fastapi import APIRouter, HTTPException

from core.schemas import ErrorDetail
from workeringestion import service
from workeringestion.schemas import EnergyReading

sites_router = APIRouter(prefix="/api/v1/sites", tags=["Worker Ingestion"])


@sites_router.get(
    "/{site_id}/current",
    response_model=EnergyReading,
    summary="Dernière lecture connue d'un site",
    description=(
        "Retourne la dernière mesure connue d'un site (consommation, tension, "
        "température...). Les champs de mesure peuvent être `null` en cas de "
        "panne capteur ou de perte réseau : `data_quality` et `null_reasons` "
        "indiquent alors la cause, sans que la lecture soit filtrée."
    ),
    responses={404: {"model": ErrorDetail, "description": "Site inexistant"}},
)
async def get_site_current_reading(site_id: str) -> EnergyReading:
    try:
        return await service.get_current_reading(site_id)
    except service.SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
