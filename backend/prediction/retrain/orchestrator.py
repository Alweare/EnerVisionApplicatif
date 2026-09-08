from __future__ import annotations

import logging

import mlflow
from mlflow.tracking import MlflowClient

from prediction.config import PredictionSettings, get_settings
from prediction.dataset.dataset import build_dataset, clean_dataset
from prediction.drift.drift_service import detect_drift
from prediction.registry import model_registry as registry
from prediction.retrain import signals
from prediction.retrain.decision import RetrainDecision, should_retrain
from prediction.training.pipeline import TrainingPipelineResult, run_training_pipeline

logger = logging.getLogger(__name__)


def train_if_needed(
    settings: PredictionSettings | None = None,
) -> tuple[RetrainDecision, TrainingPipelineResult | None]:
    settings = settings or get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)
    client = MlflowClient()

    df = build_dataset()
    clean_df = clean_dataset(df)

    champion_version = registry.get_champion_version(client, settings.mlflow_model_name)

    drift_result = None
    if champion_version is not None:
        champion_reference = registry.load_drift_reference(client, champion_version)
        if champion_reference is not None:
            drift_result = detect_drift(champion_reference, clean_df, settings.drift_threshold)

    n_new_rows = signals.count_new_rows_since_champion(client, champion_version, clean_df)
    real_performance = signals.compute_real_performance(client, champion_version)

    decision = should_retrain(
        has_champion=champion_version is not None,
        drift_result=drift_result,
        n_new_rows=n_new_rows,
        min_new_rows=settings.min_new_rows,
        real_performance=real_performance,
    )

    logger.info(
        "retrain decision",
        extra={
            "event": "retrain_decision",
            "should_retrain": decision.should_retrain,
            "retrain_reason": ",".join(decision.reasons) if decision.reasons else "none",
            "n_new_rows": n_new_rows,
            "min_new_rows": settings.min_new_rows,
            "drift_detected": drift_result.drift_detected if drift_result else None,
        },
    )

    if not decision.should_retrain:
        return decision, None

    result = run_training_pipeline(
        settings=settings,
        trigger_source="cli_train_if_needed",
        retrain_reasons=decision.reasons,
    )
    return decision, result
