from __future__ import annotations

import logging
from dataclasses import dataclass

import mlflow
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.metrics import mean_absolute_error

from prediction.config import CHAMPION_ALIAS, PredictionSettings, get_settings
from prediction.dataset.dataset import (
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_dataset,
    split_train_val_test,
)
from prediction.drift.drift_service import DriftResult, compute_reference_stats, detect_drift
from prediction.registry import model_registry as registry
from prediction.training.baseline import baseline_mae, relative_improvement
from prediction.training.training_service import train_model

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TrainingPipelineResult:
    run_id: str
    model_version: str
    mae: float
    validation_mae: float
    baseline_mae: float
    mae_improvement_vs_baseline: float
    champion_mae: float | None
    mae_improvement_vs_champion: float | None
    promoted: bool
    reason: str
    champion_unavailable: bool
    drift_result: DriftResult | None
    n_train_rows: int
    n_validation_rows: int
    n_test_rows: int


def _dataset_max_date(*frames: pd.DataFrame) -> str:
    dates = [frame["measurement_date"].max() for frame in frames if len(frame)]
    return max(dates).isoformat()


def run_training_pipeline(
    settings: PredictionSettings | None = None,
    trigger_source: str = "cli_train",
    retrain_reasons: list[str] | None = None,
) -> TrainingPipelineResult:
    settings = settings or get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(settings.mlflow_experiment_name)
    client = MlflowClient()

    logger.info("dataset build started", extra={"event": "dataset_build_started"})
    df = build_dataset()
    train, validation, test = split_train_val_test(df)
    logger.info(
        "dataset build finished",
        extra={
            "event": "dataset_build_finished",
            "n_train_rows": len(train),
            "n_validation_rows": len(validation),
            "n_test_rows": len(test),
        },
    )

    X_train, y_train = train[FEATURE_COLUMNS], train[TARGET_COLUMN]
    X_validation, y_validation = validation[FEATURE_COLUMNS], validation[TARGET_COLUMN]
    X_test, y_test = test[FEATURE_COLUMNS], test[TARGET_COLUMN]

    champion_version = registry.get_champion_version(client, settings.mlflow_model_name)

    reference_stats = compute_reference_stats(train, FEATURE_COLUMNS)
    drift_result: DriftResult | None = None
    if champion_version is not None:
        champion_reference = registry.load_drift_reference(client, champion_version)
        if champion_reference is not None:
            drift_result = detect_drift(champion_reference, test, settings.drift_threshold)
            logger.info(
                "drift computed",
                extra={
                    "event": "drift_computed",
                    "drift_detected": drift_result.drift_detected,
                    "drift_score": max(drift_result.feature_scores.values(), default=0.0),
                },
            )

    try:
        logger.info("training started", extra={"event": "training_started"})
        model, run_id, model_uri = train_model(X_train, y_train)
    except Exception:
        logger.exception("training failed", extra={"event": "training_failed"})
        raise

    test_mae = mean_absolute_error(y_test, model.predict(X_test))
    validation_mae = mean_absolute_error(y_validation, model.predict(X_validation))
    test_baseline_mae = baseline_mae(X_test, y_test)
    improvement_vs_baseline = relative_improvement(test_baseline_mae, test_mae)

    champion_mae_on_test: float | None = None
    improvement_vs_champion: float | None = None
    champion_unavailable = False
    if champion_version is not None:
        try:
            champion_model = registry.load_champion_model(settings.mlflow_model_name)
            champion_mae_on_test = mean_absolute_error(y_test, champion_model.predict(X_test))
            improvement_vs_champion = relative_improvement(champion_mae_on_test, test_mae)
        except registry.ChampionLoadError as error:
            champion_unavailable = True
            logger.error(
                "champion is registered but its model artifact could not be loaded, "
                "treating this run as a service-recovery candidate",
                extra={
                    "event": "champion_unavailable",
                    "model_name": settings.mlflow_model_name,
                    "model_version": champion_version.version,
                    "model_alias": CHAMPION_ALIAS,
                    "run_id": champion_version.run_id,
                },
                exc_info=error,
            )

    promoted, reason = _decide_promotion(
        settings=settings,
        has_champion=champion_version is not None,
        champion_unavailable=champion_unavailable,
        test_mae=test_mae,
        test_baseline_mae=test_baseline_mae,
        improvement_vs_baseline=improvement_vs_baseline,
        champion_mae_on_test=champion_mae_on_test,
        improvement_vs_champion=improvement_vs_champion,
    )

    with mlflow.start_run(run_id=run_id):
        mlflow.log_param("n_validation_rows", len(validation))
        mlflow.log_param("n_test_rows", len(test))
        mlflow.log_param("dataset_max_date", _dataset_max_date(train, validation, test))
        mlflow.log_metric("mae", test_mae)
        mlflow.log_metric("validation_mae", validation_mae)
        mlflow.log_metric("baseline_mae", test_baseline_mae)
        mlflow.log_metric("mae_improvement_vs_baseline", improvement_vs_baseline)
        if champion_mae_on_test is not None:
            mlflow.log_metric("champion_mae", champion_mae_on_test)
            mlflow.log_metric("mae_improvement_vs_champion", improvement_vs_champion)
        if drift_result is not None:
            for feature, score in drift_result.feature_scores.items():
                mlflow.log_metric(f"drift_psi_{feature}", score)
            mlflow.log_metric("drift_detected", float(drift_result.drift_detected))
        mlflow.set_tag("trigger_source", trigger_source)
        if retrain_reasons:
            mlflow.set_tag("retrain_reasons", ",".join(retrain_reasons))
        if promoted:
            registry.save_drift_reference(reference_stats)

    version = registry.register_challenger(client, settings.mlflow_model_name, model_uri)

    if promoted:
        registry.promote_to_champion(client, settings.mlflow_model_name, version.version, reason)
        if champion_unavailable:
            client.set_model_version_tag(
                settings.mlflow_model_name, version.version, "recovered_from_broken_champion", "true"
            )
    else:
        registry.reject_challenger(client, settings.mlflow_model_name, version.version, reason)

    logger.info(
        "candidate evaluated",
        extra={
            "event": "candidate_evaluated",
            "run_id": run_id,
            "model_name": settings.mlflow_model_name,
            "model_version": version.version,
            "mae": test_mae,
            "baseline_mae": test_baseline_mae,
            "champion_mae": champion_mae_on_test,
            "promoted": promoted,
        },
    )

    return TrainingPipelineResult(
        run_id=run_id,
        model_version=str(version.version),
        mae=test_mae,
        validation_mae=validation_mae,
        baseline_mae=test_baseline_mae,
        mae_improvement_vs_baseline=improvement_vs_baseline,
        champion_mae=champion_mae_on_test,
        mae_improvement_vs_champion=improvement_vs_champion,
        promoted=promoted,
        reason=reason,
        champion_unavailable=champion_unavailable,
        drift_result=drift_result,
        n_train_rows=len(train),
        n_validation_rows=len(validation),
        n_test_rows=len(test),
    )


def _decide_promotion(
    settings: PredictionSettings,
    has_champion: bool,
    champion_unavailable: bool,
    test_mae: float,
    test_baseline_mae: float,
    improvement_vs_baseline: float,
    champion_mae_on_test: float | None,
    improvement_vs_champion: float | None,
) -> tuple[bool, str]:
    if improvement_vs_baseline < settings.min_improvement_vs_baseline:
        return False, (
            f"candidate mae={test_mae:.4f} does not beat baseline_mae={test_baseline_mae:.4f} "
            f"by the required {settings.min_improvement_vs_baseline:.1%} "
            f"(actual={improvement_vs_baseline:.1%})"
        )

    if not has_champion:
        return True, "no existing champion, candidate beats the baseline"

    if champion_unavailable:
        return True, (
            "existing champion model could not be loaded (artifact unavailable); "
            f"candidate beats baseline_mae={test_baseline_mae:.4f}, promoted to restore a usable champion"
        )

    if improvement_vs_champion is not None and improvement_vs_champion >= settings.min_improvement_vs_champion:
        return True, (
            f"candidate mae={test_mae:.4f} beats champion_mae={champion_mae_on_test:.4f} "
            f"by the required {settings.min_improvement_vs_champion:.1%} "
            f"(actual={improvement_vs_champion:.1%})"
        )

    return False, (
        f"candidate mae={test_mae:.4f} does not beat champion_mae={champion_mae_on_test:.4f} "
        f"by the required {settings.min_improvement_vs_champion:.1%} "
        f"(actual={improvement_vs_champion:.1%})"
    )
