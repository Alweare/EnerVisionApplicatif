"""
Construction du scheduler de forecast (§Scheduled forecasting).

Démarré/arrêté uniquement depuis le lifespan FastAPI (`api/app.py`) --
jamais au simple import de ce module (`create_scheduler()` ne fait rien tant
qu'on ne l'appelle pas explicitement, et ne démarre rien elle-même : c'est
l'appelant qui décide de `.start()`).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from prediction.config import PredictionSettings, get_settings
from prediction.inference.prediction_service import PredictionService
from prediction.scheduler.forecast_job import run_forecast_job

logger = logging.getLogger(__name__)

FORECAST_JOB_ID = "scheduled_forecast_job"

# Si le process était occupé/indisponible au moment d'un déclenchement, on
# tolère jusqu'à 5 min de retard avant d'abandonner cette occurrence plutôt
# que de lancer un forecast basé sur un ancrage trop obsolète -- avec
# coalesce=True, plusieurs déclenchements manqués ne rattrapent qu'une seule
# exécution (jamais de rafale au retour du service), raisonnable pour un job
# horaire en MVP.
JOB_MISFIRE_GRACE_SECONDS = 300


def create_scheduler(
    settings: PredictionSettings | None = None,
    prediction_service: PredictionService | None = None,
) -> AsyncIOScheduler | None:
    """
    Renvoie un `AsyncIOScheduler` configuré mais **non démarré**, ou `None`
    si `PREDICTION_SCHEDULER_ENABLED=false` (défaut dans les tests, cf.
    tests/conftest.py). C'est à l'appelant (le lifespan FastAPI) de faire
    `.start()`/`.shutdown()`.
    """
    settings = settings or get_settings()
    if not settings.scheduler_enabled:
        logger.info("scheduled forecast disabled", extra={"event": "scheduler_disabled"})
        return None

    service = prediction_service or PredictionService(settings=settings)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_forecast_job,
        trigger="interval",
        minutes=settings.forecast_interval_minutes,
        id=FORECAST_JOB_ID,
        name="scheduled forecast (T+1h..T+{}h)".format(settings.forecast_hours),
        kwargs={"prediction_service": service, "hours": settings.forecast_hours},
        # Jamais deux exécutions concurrentes de ce job (§Concurrence) : si un
        # run dépasse l'intervalle configuré, le déclenchement suivant est
        # ignoré plutôt que lancé en parallèle.
        max_instances=1,
        coalesce=True,
        misfire_grace_time=JOB_MISFIRE_GRACE_SECONDS,
        replace_existing=True,
    )

    logger.info(
        "scheduled forecast configured",
        extra={
            "event": "scheduler_configured",
            "interval_minutes": settings.forecast_interval_minutes,
            "horizon_hours": settings.forecast_hours,
        },
    )

    return scheduler
