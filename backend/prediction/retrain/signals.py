from __future__ import annotations

import logging

import pandas as pd
from mlflow.entities.model_registry import ModelVersion
from mlflow.tracking import MlflowClient
from sklearn.metrics import mean_absolute_error

from prediction.registry import model_registry as registry
from prediction.repository.prediction_repository import get_matched_predictions
from prediction.retrain.decision import RealPerformance

logger = logging.getLogger(__name__)

MIN_MATCHED_PREDICTIONS_FOR_REAL_PERFORMANCE = 30


def count_new_rows_since_champion(
    client: MlflowClient, champion_version: ModelVersion | None, clean_df: pd.DataFrame
) -> int:
    if champion_version is None:
        return len(clean_df)

    cutoff = registry.get_run_param(client, champion_version.run_id, registry.TRAINING_CUTOFF_PARAM)
    if cutoff is None:
        return len(clean_df)

    cutoff_date = pd.Timestamp(cutoff)
    return int((clean_df["measurement_date"] > cutoff_date).sum())


def compute_real_performance(
    client: MlflowClient, champion_version: ModelVersion | None
) -> RealPerformance | None:
    if champion_version is None:
        return None

    matched = get_matched_predictions(champion_version.version)
    if len(matched) < MIN_MATCHED_PREDICTIONS_FOR_REAL_PERFORMANCE:
        logger.info(
            "not enough ground truth to compute real recent performance",
            extra={
                "event": "real_performance_unavailable",
                "model_version": champion_version.version,
                "matched_rows": len(matched),
                "required_rows": MIN_MATCHED_PREDICTIONS_FOR_REAL_PERFORMANCE,
            },
        )
        return None

    reference_mae = registry.get_run_metric(client, champion_version.run_id, "mae")
    if reference_mae is None:
        return None

    real_mae = mean_absolute_error(matched["consumption_kw"], matched["predicted_consumption_kw"])
    return RealPerformance(matched_rows=len(matched), real_mae=real_mae, reference_mae=reference_mae)
