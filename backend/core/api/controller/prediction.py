from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.api.schemas import SitePredictionRead
from core.api.service.prediction_service import (
    PredictionNotAvailableError,
    PredictionService,
    SiteNotFoundError,
)
from shared.database import get_db
from core.schemas import ErrorDetail

router = APIRouter(prefix="/api/v1/backend/sites", tags=["Predictions"])


@router.get(
    "/{site_id}/predictions",
    summary="Prédiction de consommation d'un site",
    description=(
        "Retourne la projection horaire à venir, le prochain pic prévu, le "
        "modèle qui l'a produite, et l'historique récent agrégé à l'heure pour "
        "le tracé. Les prédictions sont précalculées à partir du modèle MLflow "
        "et stockées dans `ener.prediction`."
    ),
    responses={
        404: {
            "model": ErrorDetail,
            "description": "Site inexistant",
        },
        503: {
            "model": ErrorDetail,
            "description": "Aucune prédiction disponible pour ce site",
        },
    },
)
def get_site_predictions(
    site_id: str,
    db: Annotated[Session, Depends(get_db)],
    history_hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> SitePredictionRead:
    service = PredictionService(db)
    try:
        return service.get_prediction(site_id, history_hours=history_hours)
    except SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PredictionNotAvailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
