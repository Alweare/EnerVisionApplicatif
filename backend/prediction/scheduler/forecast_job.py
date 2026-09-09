"""
Job de forecast planifié (§Scheduled forecasting).

Un déclencheur, rien de plus : construit la liste des sites via
`repository/site_repository.py` et appelle `PredictionService.forecast(...)`
pour chacun -- exactement le chemin déjà emprunté par
`GET /api/v1/sites/{site_id}/forecast` (chargement du champion MLflow,
construction des features, persistance via `PredictionRepository`). Aucune
logique ML, aucun accès direct aux données, aucune décision de promotion
n'est dupliquée ici.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from prediction.inference.prediction_service import PredictionService
from prediction.observability.ml_metrics import observe_scheduled_forecast_job
from prediction.repository.site_repository import get_active_site_ids

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForecastJobResult:
    n_sites: int
    n_success: int
    n_failed: int
    failed_site_ids: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def run_forecast_job(prediction_service: PredictionService, hours: int) -> ForecastJobResult:
    """
    Génère un forecast de `hours` heures pour chaque site actif et le
    persiste (via `PredictionService.forecast(..., persist=True)`, donc via
    `PredictionRepository`). Une erreur sur un site est loguée avec son
    `site_id` et n'empêche jamais le traitement des sites suivants.
    """
    started_at = time.perf_counter()
    site_ids = get_active_site_ids()

    logger.info(
        "scheduled forecast job started",
        extra={
            "event": "scheduled_forecast_job_started",
            "n_sites": len(site_ids),
            "horizon_hours": hours,
        },
    )

    failed_site_ids: list[str] = []
    for site_id in site_ids:
        try:
            prediction_service.forecast(site_id, hours=hours)
        except Exception:
            failed_site_ids.append(site_id)
            logger.exception(
                "scheduled forecast failed for site",
                extra={
                    "event": "scheduled_forecast_job_site_failed",
                    "site_id": site_id,
                    "horizon_hours": hours,
                },
            )

    duration_seconds = time.perf_counter() - started_at
    n_failed = len(failed_site_ids)
    n_success = len(site_ids) - n_failed

    result = ForecastJobResult(
        n_sites=len(site_ids),
        n_success=n_success,
        n_failed=n_failed,
        failed_site_ids=failed_site_ids,
        duration_seconds=duration_seconds,
    )

    logger.info(
        "scheduled forecast job finished",
        extra={
            "event": "scheduled_forecast_job_finished",
            "n_sites": result.n_sites,
            "n_success": result.n_success,
            "n_failed": result.n_failed,
            "duration_seconds": result.duration_seconds,
        },
    )

    try:
        observe_scheduled_forecast_job(n_success, n_failed, duration_seconds)
    except Exception:
        logger.exception(
            "failed to record scheduled forecast job metrics",
            extra={"event": "scheduled_forecast_job_metrics_failed"},
        )

    return result
