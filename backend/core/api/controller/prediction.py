from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.api.schemas import PredictionRead
from core.api.service.prediction_service import (
    ModelNotAvailableError,
    PredictionService,
    SiteNotFoundError,
)
from shared.database import get_db
from core.schemas import ErrorDetail

router = APIRouter(prefix="/api/v1/backend/prediction", tags=["Predictions"])


@router.get(
    "/{site_id}",
    response_model=PredictionRead,
    summary="Prédiction de consommation d'un site",
    description=(
        "Retourne la prédiction de consommation la plus récente pour un site, "
        "calculée à partir du modèle MLflow `consumption-predictor`."
    ),
    responses={
        404: {
            "model": ErrorDetail,
            "description": "Site inexistant",
        },
        503: {
            "model": ErrorDetail,
            "description": "Aucun modèle de prédiction disponible",
        },
    },
)
def get_site_prediction(
    site_id: str,
    db: Session = Depends(get_db),
) -> PredictionRead:
    service = PredictionService(db)
    try:
        return service.get_prediction(site_id)
    except SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ModelNotAvailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
