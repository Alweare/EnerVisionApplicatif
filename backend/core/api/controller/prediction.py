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
    response_model=SitePredictionRead,
    summary="Prédiction de consommation d'un site",
    description=(
        "Retourne le pic de consommation prévu pour un site (échéance la plus "
        "chargée à venir), le modèle qui l'a produit, et l'historique récent "
        "des mesures pour le tracé. Les prédictions sont précalculées à partir "
        "du modèle MLflow et stockées dans `ener.prediction`."
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
    history_limit: int = Query(default=200, ge=0, le=2000),
    db: Session = Depends(get_db),
) -> SitePredictionRead:
    service = PredictionService(db)
    try:
        return service.get_prediction(site_id, history_limit=history_limit)
    except SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PredictionNotAvailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
