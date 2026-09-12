from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.api.schemas import MeasurementRead
from core.api.service.measurement_service import (
    MeasurementNotFoundError,
    MeasurementService,
    SiteNotFoundError,
)
from shared.database import get_db
from core.schemas import ErrorDetail

router = APIRouter(prefix="/api/v1/backend/sites", tags=["Measurements"])


@router.get(
    "/{site_id}/current",
    summary="Dernière mesure d'un site",
    description=(
        "Retourne la mesure la plus récente enregistrée pour un site "
        "(d'après `measurement_date`)."
    ),
    responses={
        404: {
            "model": ErrorDetail,
            "description": "Site inexistant ou aucune mesure enregistrée",
        }
    },
)
def get_site_current_measurement(
    site_id: str,
    db: Annotated[Session, Depends(get_db)],
) -> MeasurementRead:
    service = MeasurementService(db)
    try:
        return service.get_current_measurement(site_id)
    except (SiteNotFoundError, MeasurementNotFoundError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get(
    "/{site_id}/measurements",
    summary="Mesures d'un site",
    description=(
        "Retourne les mesures d'un site, de la plus récente à la plus ancienne "
        "(d'après `measurement_date`). Paginé via `limit` et `offset`."
    ),
    responses={
        404: {
            "model": ErrorDetail,
            "description": "Site inexistant",
        }
    },
)
def list_site_measurements(
    site_id: str,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[MeasurementRead]:
    service = MeasurementService(db)
    try:
        return service.list_measurements(site_id, limit=limit, offset=offset)
    except SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
