from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.api.schemas import PredictionRead
from core.api.service.prediction_service import (
    PredictionNotAvailableError,
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
        "Retourne la prédiction de consommation courante pour un site "
        "(prochaine échéance à venir, sinon la plus récente). Les prédictions "
        "sont précalculées à partir du modèle MLflow et stockées dans "
        "`ener.prediction`."
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
def get_site_prediction(
    site_id: str,
    db: Session = Depends(get_db),
) -> PredictionRead:
    service = PredictionService(db)
    try:
        return service.get_prediction(site_id)
    except SiteNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PredictionNotAvailableError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
