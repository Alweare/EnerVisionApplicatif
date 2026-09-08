import logging
import time

from fastapi import APIRouter, Depends, HTTPException

from prediction.api.schemas import PredictionResponse
from prediction.inference.feature_builder import InsufficientHistoryError
from prediction.inference.prediction_service import NoChampionModelError, PredictionService
from prediction.observability.ml_metrics import observe_prediction_error, observe_prediction_success

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sites", tags=["Predictions"])

_service = PredictionService()


def get_prediction_service() -> PredictionService:
    return _service


@router.get(
    "/{site_id}/prediction",
    response_model=PredictionResponse,
    summary="Prédit la consommation à T+1h pour un site",
    responses={
        404: {"description": "Historique insuffisant pour ce site"},
        503: {"description": "Aucun modèle champion disponible"},
    },
)
def get_site_prediction(
    site_id: str, service: PredictionService = Depends(get_prediction_service)
) -> PredictionResponse:
    started_at = time.perf_counter()

    try:
        result = service.predict(site_id)
    except InsufficientHistoryError as error:
        observe_prediction_error("insufficient_history", time.perf_counter() - started_at)
        raise HTTPException(
            status_code=404, detail=f"Historique insuffisant pour le site '{site_id}'"
        ) from error
    except NoChampionModelError as error:
        observe_prediction_error("no_champion_model", time.perf_counter() - started_at)
        raise HTTPException(status_code=503, detail="Aucun modèle champion disponible") from error
    except Exception as error:
        observe_prediction_error("unexpected", time.perf_counter() - started_at)
        logger.exception(
            "prediction failed", extra={"event": "prediction_failed", "site_id": site_id}
        )
        raise HTTPException(status_code=500, detail="Erreur interne lors de la prédiction") from error

    observe_prediction_success(time.perf_counter() - started_at)

    return PredictionResponse(
        site_id=result.site_id,
        prediction_timestamp=result.prediction_timestamp,
        target_timestamp=result.target_timestamp,
        predicted_consumption_kw=result.predicted_consumption_kw,
        model_version=result.model_version,
    )
