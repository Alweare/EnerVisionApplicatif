from __future__ import annotations

import logging

import mlflow
from mlflow.tracking import MlflowClient
from prometheus_client import Counter, Gauge, Histogram

from prediction.config import PredictionSettings, get_settings
from prediction.registry import model_registry as registry

logger = logging.getLogger(__name__)

PREDICTION_REQUESTS_TOTAL = Counter(
    "prediction_requests_total", "Nombre de prédictions servies", ["result"]
)
PREDICTION_ERRORS_TOTAL = Counter(
    "prediction_errors_total", "Nombre d'erreurs de prédiction", ["reason"]
)
PREDICTION_LATENCY_SECONDS = Histogram(
    "prediction_latency_seconds", "Latence des prédictions"
)
ML_LAST_PREDICTION_TIMESTAMP = Gauge(
    "ml_last_prediction_timestamp", "Timestamp Unix de la dernière prédiction servie"
)

# Forecast multi-horizon (§14 du besoin) : mêmes principes que les métriques
# prediction_* ci-dessus (pas de label site_id/timestamp/run_id -- cardinalité
# maîtrisée), déclarées séparément pour distinguer /prediction de /forecast.
FORECAST_REQUESTS_TOTAL = Counter(
    "forecast_requests_total", "Nombre de forecasts multi-horizon servis", ["result"]
)
FORECAST_ERRORS_TOTAL = Counter(
    "forecast_errors_total", "Nombre d'erreurs de forecast", ["reason"]
)
FORECAST_LATENCY_SECONDS = Histogram(
    "forecast_latency_seconds", "Latence des forecasts multi-horizon"
)
FORECAST_POINTS_GENERATED_TOTAL = Counter(
    "forecast_points_generated_total", "Nombre total de points de forecast générés (toutes requêtes)"
)

# Scheduler de forecast (§Scheduled forecasting) : un run = un passage du job
# sur tous les sites actifs. Pas de label site_id (cardinalité) -- le détail
# par site reste dans les logs (§Gestion des erreurs).
SCHEDULED_FORECAST_JOB_RUNS_TOTAL = Counter(
    "scheduled_forecast_job_runs_total", "Nombre d'exécutions du job de forecast planifié"
)
SCHEDULED_FORECAST_JOB_SITES_TOTAL = Counter(
    "scheduled_forecast_job_sites_total",
    "Nombre de sites traités par le job de forecast planifié",
    ["result"],
)
SCHEDULED_FORECAST_JOB_DURATION_SECONDS = Histogram(
    "scheduled_forecast_job_duration_seconds", "Durée totale d'une exécution du job de forecast planifié"
)
SCHEDULED_FORECAST_JOB_LAST_SUCCESS_TIMESTAMP = Gauge(
    "scheduled_forecast_job_last_success_timestamp",
    "Timestamp Unix de la dernière exécution du job de forecast planifié sans erreur inattendue",
)

ML_TRAINING_RUNS_TOTAL = Gauge(
    "ml_training_runs_total", "Nombre de runs d'entraînement enregistrés dans MLflow"
)
ML_TRAINING_FAILURES_TOTAL = Gauge(
    "ml_training_failures_total", "Nombre de runs d'entraînement en échec"
)
ML_MODEL_PROMOTIONS_TOTAL = Gauge(
    "ml_model_promotions_total", "Nombre de versions promues champion"
)
ML_MODEL_REJECTIONS_TOTAL = Gauge(
    "ml_model_rejections_total", "Nombre de challengers rejetés"
)
ML_RETRAINING_TRIGGERED_TOTAL = Gauge(
    "ml_retraining_triggered_total", "Nombre de runs déclenchés par train-if-needed"
)
ML_LAST_TRAINING_MAE = Gauge("ml_last_training_mae", "MAE du run d'entraînement le plus récent (T+1h)")
ML_BASELINE_MAE = Gauge("ml_baseline_mae", "MAE de la baseline lors du run le plus récent (T+1h)")
ML_CHAMPION_MAE = Gauge("ml_champion_mae", "MAE du modèle champion actuel (T+1h)")

# Horizons clés (§14 du besoin) : mêmes gauges que ci-dessus, à T+24h et T+48h
# -- permet de voir dans Grafana la dégradation de la MAE avec l'horizon,
# jamais masquée par une seule MAE globale (cf. §7/§17 du besoin).
ML_MAE_H24 = Gauge("ml_mae_h24", "MAE du run d'entraînement le plus récent à T+24h")
ML_MAE_H48 = Gauge("ml_mae_h48", "MAE du run d'entraînement le plus récent à T+48h")
ML_BASELINE_MAE_H24 = Gauge("ml_baseline_mae_h24", "MAE de la baseline lors du run le plus récent à T+24h")
ML_BASELINE_MAE_H48 = Gauge("ml_baseline_mae_h48", "MAE de la baseline lors du run le plus récent à T+48h")
ML_DRIFT_SCORE = Gauge(
    "ml_drift_score", "Score PSI de dérive par feature lors du run le plus récent", ["feature"]
)
ML_DRIFT_DETECTED = Gauge(
    "ml_drift_detected", "1 si une dérive a été détectée lors du run le plus récent"
)
ML_LAST_SUCCESSFUL_TRAINING_TIMESTAMP = Gauge(
    "ml_last_successful_training_timestamp", "Timestamp Unix du run d'entraînement le plus récent"
)
ML_CURRENT_MODEL_INFO = Gauge(
    "ml_current_model_info", "Version du modèle champion actuellement chargé",
    ["model_name", "alias", "version"],
)


def observe_prediction_success(latency_seconds: float) -> None:
    PREDICTION_REQUESTS_TOTAL.labels(result="success").inc()
    PREDICTION_LATENCY_SECONDS.observe(latency_seconds)
    ML_LAST_PREDICTION_TIMESTAMP.set_to_current_time()


def observe_prediction_error(reason: str, latency_seconds: float) -> None:
    PREDICTION_REQUESTS_TOTAL.labels(result="error").inc()
    PREDICTION_ERRORS_TOTAL.labels(reason=reason).inc()
    PREDICTION_LATENCY_SECONDS.observe(latency_seconds)


def observe_forecast_success(latency_seconds: float, n_points: int) -> None:
    FORECAST_REQUESTS_TOTAL.labels(result="success").inc()
    FORECAST_LATENCY_SECONDS.observe(latency_seconds)
    FORECAST_POINTS_GENERATED_TOTAL.inc(n_points)
    ML_LAST_PREDICTION_TIMESTAMP.set_to_current_time()


def observe_forecast_error(reason: str, latency_seconds: float) -> None:
    FORECAST_REQUESTS_TOTAL.labels(result="error").inc()
    FORECAST_ERRORS_TOTAL.labels(reason=reason).inc()
    FORECAST_LATENCY_SECONDS.observe(latency_seconds)


def observe_scheduled_forecast_job(n_success: int, n_failed: int, duration_seconds: float) -> None:
    """Appelé une fois par exécution du job planifié (jamais par site :
    cardinalité, cf. commentaire sur les métriques ci-dessus)."""
    SCHEDULED_FORECAST_JOB_RUNS_TOTAL.inc()
    SCHEDULED_FORECAST_JOB_SITES_TOTAL.labels(result="success").inc(n_success)
    SCHEDULED_FORECAST_JOB_SITES_TOTAL.labels(result="failure").inc(n_failed)
    SCHEDULED_FORECAST_JOB_DURATION_SECONDS.observe(duration_seconds)
    SCHEDULED_FORECAST_JOB_LAST_SUCCESS_TIMESTAMP.set_to_current_time()


def refresh_ml_metrics(settings: PredictionSettings | None = None) -> None:
    settings = settings or get_settings()
    try:
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        client = MlflowClient()

        experiment = mlflow.get_experiment_by_name(settings.mlflow_experiment_name)
        if experiment is not None:
            _refresh_experiment_metrics(client, experiment.experiment_id)

        _refresh_registry_metrics(client, settings.mlflow_model_name)
    except Exception:
        logger.exception("failed to refresh ml metrics", extra={"event": "ml_metrics_refresh_failed"})


def _refresh_experiment_metrics(client: MlflowClient, experiment_id: str) -> None:
    trained_runs = registry.count_runs_with_tag(
        client, experiment_id, "trigger_source", "cli_train"
    ) + registry.count_runs_with_tag(client, experiment_id, "trigger_source", "cli_train_if_needed")
    ML_TRAINING_RUNS_TOTAL.set(trained_runs)

    ML_TRAINING_FAILURES_TOTAL.set(
        registry.count_runs_with_tag(client, experiment_id, "status", "failed")
    )
    ML_RETRAINING_TRIGGERED_TOTAL.set(
        registry.count_runs_with_tag(client, experiment_id, "trigger_source", "cli_train_if_needed")
    )

    latest_runs = client.search_runs(
        experiment_ids=[experiment_id],
        order_by=["attributes.start_time DESC"],
        max_results=1,
    )
    if not latest_runs:
        return

    latest = latest_runs[0]
    if "mae" in latest.data.metrics:
        ML_LAST_TRAINING_MAE.set(latest.data.metrics["mae"])
    if "mae_h24" in latest.data.metrics:
        ML_MAE_H24.set(latest.data.metrics["mae_h24"])
    if "mae_h48" in latest.data.metrics:
        ML_MAE_H48.set(latest.data.metrics["mae_h48"])
    if "baseline_mae_h24" in latest.data.metrics:
        ML_BASELINE_MAE_H24.set(latest.data.metrics["baseline_mae_h24"])
    if "baseline_mae_h48" in latest.data.metrics:
        ML_BASELINE_MAE_H48.set(latest.data.metrics["baseline_mae_h48"])
    if "baseline_mae" in latest.data.metrics:
        ML_BASELINE_MAE.set(latest.data.metrics["baseline_mae"])
    if "drift_detected" in latest.data.metrics:
        ML_DRIFT_DETECTED.set(latest.data.metrics["drift_detected"])
    for key, value in latest.data.metrics.items():
        if key.startswith("drift_psi_"):
            ML_DRIFT_SCORE.labels(feature=key[len("drift_psi_"):]).set(value)
    if latest.info.start_time:
        ML_LAST_SUCCESSFUL_TRAINING_TIMESTAMP.set(latest.info.start_time / 1000)


def _refresh_registry_metrics(client: MlflowClient, model_name: str) -> None:
    ML_MODEL_PROMOTIONS_TOTAL.set(registry.count_versions_with_tag(client, model_name, "promoted", "true"))
    ML_MODEL_REJECTIONS_TOTAL.set(registry.count_versions_with_tag(client, model_name, "rejected", "true"))

    champion = registry.get_champion_version(client, model_name)
    if champion is None:
        return

    ML_CURRENT_MODEL_INFO.labels(model_name=model_name, alias="champion", version=str(champion.version)).set(1)
    champion_mae = registry.get_run_metric(client, champion.run_id, "mae")
    if champion_mae is not None:
        ML_CHAMPION_MAE.set(champion_mae)
