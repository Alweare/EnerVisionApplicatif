import logging
import time
from contextlib import contextmanager
#test
from fastapi import APIRouter, Depends, HTTPException, Query

from prediction.api.schemas import ForecastPoint, ForecastResponse, PredictionResponse
from prediction.dataset.dataset import MAX_HORIZON_HOURS
from prediction.inference.feature_builder import InsufficientHistoryError
from prediction.inference.prediction_service import NoChampionModelError, PredictionService
from prediction.observability.ml_metrics import (
    observe_forecast_error,
    observe_forecast_success,
    observe_prediction_error,
    observe_prediction_success,
)
from prediction.registry.model_registry import ChampionLoadError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sites", tags=["Predictions"])

_service = PredictionService()

_NOT_FOUND_DESCRIPTION = "Historique insuffisant pour ce site"
_UNAVAILABLE_DESCRIPTION = "Aucun modèle champion disponible ou champion inaccessible"


def get_prediction_service() -> PredictionService:
    return _service


@contextmanager
def _map_inference_errors(site_id: str, observe_error):
    """
    Traduit les exceptions métier de la couche d'inférence en codes HTTP,
    partagée par `/prediction` et `/forecast` pour rester DRY sans mettre de
    logique ML dans le contrôleur.
    """
    started_at = time.perf_counter()
    try:
        yield
    except InsufficientHistoryError as error:
        observe_error("insufficient_history", time.perf_counter() - started_at)
        raise HTTPException(
            status_code=404, detail=f"Historique insuffisant pour le site '{site_id}'"
        ) from error
    except NoChampionModelError as error:
        observe_error("no_champion_model", time.perf_counter() - started_at)
        raise HTTPException(status_code=503, detail="Aucun modèle champion disponible") from error
    except ChampionLoadError as error:
        observe_error("champion_artifact_unavailable", time.perf_counter() - started_at)
        logger.error(
            "champion model registered but its artifact is unavailable",
            extra={"event": "champion_unavailable", "site_id": site_id},
            exc_info=error,
        )
        raise HTTPException(
            status_code=503,
            detail="Modèle champion enregistré mais son artefact est indisponible",
        ) from error
    except HTTPException:
        raise
    except Exception as error:
        observe_error("unexpected", time.perf_counter() - started_at)
        logger.exception(
            "inference failed", extra={"event": "inference_failed", "site_id": site_id}
        )
        raise HTTPException(status_code=500, detail="Erreur interne lors de la prédiction") from error


@router.get(
    "/{site_id}/prediction",
    response_model=PredictionResponse,
    summary="Prédit la consommation à T+1h pour un site",
    responses={
        404: {"description": _NOT_FOUND_DESCRIPTION},
        503: {"description": _UNAVAILABLE_DESCRIPTION},
    },
)
def get_site_prediction(
    site_id: str, service: PredictionService = Depends(get_prediction_service)
) -> PredictionResponse:
    started_at = time.perf_counter()

    with _map_inference_errors(site_id, observe_prediction_error):
        result = service.predict(site_id)

    observe_prediction_success(time.perf_counter() - started_at)

    return PredictionResponse(
        site_id=result.site_id,
        prediction_timestamp=result.prediction_timestamp,
        target_timestamp=result.target_timestamp,
        predicted_consumption_kw=result.predicted_consumption_kw,
        model_version=result.model_version,
    )


@router.get(
    "/{site_id}/forecast",
    response_model=ForecastResponse,
    summary="Prévision horaire de consommation de T+1h à T+`hours`h (2 jours max)",
    responses={
        404: {"description": _NOT_FOUND_DESCRIPTION},
        503: {"description": _UNAVAILABLE_DESCRIPTION},
        422: {"description": f"hours hors de la plage autorisée (1 à {MAX_HORIZON_HOURS})"},
    },
)
def get_site_forecast(
    site_id: str,
    hours: int = Query(
        24, ge=1, le=MAX_HORIZON_HOURS, description=f"Horizon en heures, de 1 à {MAX_HORIZON_HOURS} (2 jours)."
    ),
    service: PredictionService = Depends(get_prediction_service),
) -> ForecastResponse:
    started_at = time.perf_counter()

    with _map_inference_errors(site_id, observe_forecast_error):
        result = service.forecast(site_id, hours)

    observe_forecast_success(time.perf_counter() - started_at, n_points=len(result.points))

    return ForecastResponse(
        site_id=result.site_id,
        generated_at=result.generated_at,
        base_timestamp=result.base_timestamp,
        horizon_hours=result.horizon_hours,
        model_version=result.model_version,
        predictions=[
            ForecastPoint(
                horizon_hours=point.horizon_hours,
                target_timestamp=point.target_timestamp,
                predicted_consumption_kw=point.predicted_consumption_kw,
            )
            for point in result.points
        ],
    )
