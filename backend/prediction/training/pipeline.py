from __future__ import annotations

import logging
from dataclasses import dataclass

import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient
from sklearn.metrics import mean_absolute_error

from prediction.config import CHAMPION_ALIAS, PredictionSettings, get_settings
from prediction.dataset.dataset import (
    DRIFT_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    HORIZONS_HOURS,
    KEY_HORIZONS_HOURS,
    MAX_HORIZON_HOURS,
    MULTI_HORIZON_TARGET_COLUMNS,
    TARGET_COLUMN_PREFIX,
    build_dataset,
    split_train_val_test_multi_horizon,
)
from prediction.drift.drift_service import DriftResult, compute_reference_stats, detect_drift
from prediction.registry import model_registry as registry
from prediction.training.baseline import attach_baseline_columns, multi_horizon_baseline_mae, relative_improvement
from prediction.training.training_service import train_model

logger = logging.getLogger(__name__)

MAE_BY_HORIZON_ARTIFACT_PATH = "mae_by_horizon.json"


@dataclass(frozen=True)
class TrainingPipelineResult:
    run_id: str
    model_version: str

    # Détail complet (1..48h), exposé en Python et loggé en artefact MLflow
    # (jamais en 48 métriques MLflow séparées -- resterait illisible, §7 du besoin).
    mae_by_horizon: dict[int, float]
    baseline_mae_by_horizon: dict[int, float]

    # Horizons clés (§7/§9 du besoin), aussi loggés comme métriques MLflow scalaires.
    mae_h1: float
    mae_h24: float
    mae_h48: float
    baseline_mae_h1: float
    baseline_mae_h24: float
    baseline_mae_h48: float
    mae_mean: float
    mae_improvement_vs_baseline_by_key_horizon: dict[int, float]

    # Alias rétro-compatibles (= valeurs *_h1) : préservent le comportement du
    # modèle T+1h historique pour le code/les métriques qui en dépendent déjà
    # (main.py, observability/ml_metrics.py, tests existants).
    mae: float
    baseline_mae: float
    mae_improvement_vs_baseline: float
    validation_mae: float

    champion_mae: float | None
    champion_mae_by_key_horizon: dict[int, float] | None
    mae_improvement_vs_champion: float | None
    mae_improvement_vs_champion_by_key_horizon: dict[int, float] | None

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


def _mae_by_horizon(Y_true: pd.DataFrame, predictions) -> dict[int, float]:
    """
    MAE par horizon à partir des 48 colonnes cibles et de la sortie du modèle
    multi-output (mêmes colonnes, même ordre que `MULTI_HORIZON_TARGET_COLUMNS`
    -- l'ordre est fixé une fois pour toutes par `HORIZONS_HOURS`, utilisé à la
    fois pour construire Y_train à l'entraînement et pour interpréter la sortie
    de `model.predict(...)` ici comme à l'inférence).
    """
    predictions = np.asarray(predictions)
    return {
        horizon_hours: mean_absolute_error(
            Y_true[f"{TARGET_COLUMN_PREFIX}{horizon_hours}"], predictions[:, idx]
        )
        for idx, horizon_hours in enumerate(HORIZONS_HOURS)
    }


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
    # Colonnes baseline_h{h} calculées sur la série continue, avant tout split
    # (un lag saisonnier calculé après découpage serait tronqué près du début
    # de chaque tranche -- cf. training/baseline.py).
    df = attach_baseline_columns(df, HORIZONS_HOURS)
    train, validation, test = split_train_val_test_multi_horizon(df)
    logger.info(
        "dataset build finished",
        extra={
            "event": "dataset_build_finished",
            "n_train_rows": len(train),
            "n_validation_rows": len(validation),
            "n_test_rows": len(test),
        },
    )

    X_train, Y_train = train[FEATURE_COLUMNS], train[MULTI_HORIZON_TARGET_COLUMNS]
    X_validation, Y_validation = validation[FEATURE_COLUMNS], validation[MULTI_HORIZON_TARGET_COLUMNS]
    X_test, Y_test = test[FEATURE_COLUMNS], test[MULTI_HORIZON_TARGET_COLUMNS]

    champion_version = registry.get_champion_version(client, settings.mlflow_model_name)

    reference_stats = compute_reference_stats(train, DRIFT_FEATURE_COLUMNS)
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
        model, run_id, model_uri = train_model(X_train, Y_train)
    except Exception:
        logger.exception("training failed", extra={"event": "training_failed"})
        raise

    mae_by_horizon = _mae_by_horizon(Y_test, model.predict(X_test))
    validation_mae_by_horizon = _mae_by_horizon(Y_validation, model.predict(X_validation))
    baseline_mae_by_horizon = multi_horizon_baseline_mae(test, HORIZONS_HOURS)

    mae_by_key_horizon = {h: mae_by_horizon[h] for h in KEY_HORIZONS_HOURS}
    baseline_mae_by_key_horizon = {h: baseline_mae_by_horizon[h] for h in KEY_HORIZONS_HOURS}
    mae_mean = float(np.mean(list(mae_by_horizon.values())))
    improvement_vs_baseline_by_key_horizon = {
        h: relative_improvement(baseline_mae_by_key_horizon[h], mae_by_key_horizon[h])
        for h in KEY_HORIZONS_HOURS
    }

    champion_mae_by_key_horizon: dict[int, float] | None = None
    improvement_vs_champion_by_key_horizon: dict[int, float] | None = None
    champion_unavailable = False
    if champion_version is not None:
        try:
            champion_model = registry.load_champion_model(settings.mlflow_model_name)
            champion_mae_by_horizon = _mae_by_horizon(Y_test, champion_model.predict(X_test))
            champion_mae_by_key_horizon = {h: champion_mae_by_horizon[h] for h in KEY_HORIZONS_HOURS}
            improvement_vs_champion_by_key_horizon = {
                h: relative_improvement(champion_mae_by_key_horizon[h], mae_by_key_horizon[h])
                for h in KEY_HORIZONS_HOURS
            }
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
        mae_by_key_horizon=mae_by_key_horizon,
        baseline_mae_by_key_horizon=baseline_mae_by_key_horizon,
        champion_mae_by_key_horizon=champion_mae_by_key_horizon,
    )

    with mlflow.start_run(run_id=run_id):
        mlflow.log_param("n_validation_rows", len(validation))
        mlflow.log_param("n_test_rows", len(test))
        mlflow.log_param("dataset_max_date", _dataset_max_date(train, validation, test))
        mlflow.log_param("horizons_hours", f"1-{MAX_HORIZON_HOURS}")

        # Alias rétro-compatibles (= horizon 1h).
        mlflow.log_metric("mae", mae_by_key_horizon[1])
        mlflow.log_metric("baseline_mae", baseline_mae_by_key_horizon[1])
        mlflow.log_metric("mae_improvement_vs_baseline", improvement_vs_baseline_by_key_horizon[1])
        mlflow.log_metric("validation_mae", validation_mae_by_horizon[1])

        # Horizons clés (§7/§9) : lisibles directement dans l'UI MLflow.
        mlflow.log_metric("mae_mean", mae_mean)
        for horizon_hours in KEY_HORIZONS_HOURS:
            mlflow.log_metric(f"mae_h{horizon_hours}", mae_by_key_horizon[horizon_hours])
            mlflow.log_metric(f"baseline_mae_h{horizon_hours}", baseline_mae_by_key_horizon[horizon_hours])
            mlflow.log_metric(
                f"mae_improvement_vs_baseline_h{horizon_hours}",
                improvement_vs_baseline_by_key_horizon[horizon_hours],
            )

        if champion_mae_by_key_horizon is not None:
            mlflow.log_metric("champion_mae", champion_mae_by_key_horizon[1])
            mlflow.log_metric("mae_improvement_vs_champion", improvement_vs_champion_by_key_horizon[1])
            for horizon_hours in KEY_HORIZONS_HOURS:
                mlflow.log_metric(f"champion_mae_h{horizon_hours}", champion_mae_by_key_horizon[horizon_hours])
                mlflow.log_metric(
                    f"mae_improvement_vs_champion_h{horizon_hours}",
                    improvement_vs_champion_by_key_horizon[horizon_hours],
                )

        if drift_result is not None:
            for feature, score in drift_result.feature_scores.items():
                mlflow.log_metric(f"drift_psi_{feature}", score)
            mlflow.log_metric("drift_detected", float(drift_result.drift_detected))

        # Détail des 48 horizons : artefact JSON, jamais 48 métriques MLflow
        # séparées (resterait illisible dans l'UI, §7 du besoin).
        mlflow.log_dict(
            {
                "mae_by_horizon": mae_by_horizon,
                "baseline_mae_by_horizon": baseline_mae_by_horizon,
            },
            MAE_BY_HORIZON_ARTIFACT_PATH,
        )

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
            "mae_h1": mae_by_key_horizon[1],
            "mae_h24": mae_by_key_horizon[24],
            "mae_h48": mae_by_key_horizon[MAX_HORIZON_HOURS],
            "baseline_mae_h1": baseline_mae_by_key_horizon[1],
            "champion_mae_h1": champion_mae_by_key_horizon[1] if champion_mae_by_key_horizon else None,
            "promoted": promoted,
        },
    )

    return TrainingPipelineResult(
        run_id=run_id,
        model_version=str(version.version),
        mae_by_horizon=mae_by_horizon,
        baseline_mae_by_horizon=baseline_mae_by_horizon,
        mae_h1=mae_by_key_horizon[1],
        mae_h24=mae_by_key_horizon[24],
        mae_h48=mae_by_key_horizon[MAX_HORIZON_HOURS],
        baseline_mae_h1=baseline_mae_by_key_horizon[1],
        baseline_mae_h24=baseline_mae_by_key_horizon[24],
        baseline_mae_h48=baseline_mae_by_key_horizon[MAX_HORIZON_HOURS],
        mae_mean=mae_mean,
        mae_improvement_vs_baseline_by_key_horizon=improvement_vs_baseline_by_key_horizon,
        mae=mae_by_key_horizon[1],
        baseline_mae=baseline_mae_by_key_horizon[1],
        mae_improvement_vs_baseline=improvement_vs_baseline_by_key_horizon[1],
        validation_mae=validation_mae_by_horizon[1],
        champion_mae=champion_mae_by_key_horizon[1] if champion_mae_by_key_horizon else None,
        champion_mae_by_key_horizon=champion_mae_by_key_horizon,
        mae_improvement_vs_champion=(
            improvement_vs_champion_by_key_horizon[1] if improvement_vs_champion_by_key_horizon else None
        ),
        mae_improvement_vs_champion_by_key_horizon=improvement_vs_champion_by_key_horizon,
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
    mae_by_key_horizon: dict[int, float],
    baseline_mae_by_key_horizon: dict[int, float],
    champion_mae_by_key_horizon: dict[int, float] | None,
    key_horizons: tuple[int, ...] = KEY_HORIZONS_HOURS,
) -> tuple[bool, str]:
    """
    Règle de promotion multi-horizon (§9 du besoin) : le candidat doit battre
    la baseline puis (s'il existe) le champion **simultanément** à chaque
    horizon clé (h1, h24, h48) -- pas seulement en moyenne, pour ne jamais
    promouvoir un modèle excellent à T+1h mais catastrophique à T+48h.
    `mae_mean` reste une information complémentaire (loggée dans MLflow),
    jamais un critère de décision.
    """
    improvements_vs_baseline = {
        h: relative_improvement(baseline_mae_by_key_horizon[h], mae_by_key_horizon[h]) for h in key_horizons
    }
    failing_baseline = [
        h for h in key_horizons if improvements_vs_baseline[h] < settings.min_improvement_vs_baseline
    ]
    if failing_baseline:
        details = ", ".join(
            f"h={h}h mae={mae_by_key_horizon[h]:.4f} baseline_mae={baseline_mae_by_key_horizon[h]:.4f} "
            f"(actual={improvements_vs_baseline[h]:.1%})"
            for h in failing_baseline
        )
        return False, (
            f"candidate does not beat baseline by the required {settings.min_improvement_vs_baseline:.1%} "
            f"at key horizon(s) {failing_baseline} ({details})"
        )

    if not has_champion:
        return True, "no existing champion, candidate beats the baseline at all key horizons (h1, h24, h48)"

    if champion_unavailable:
        return True, (
            "existing champion model could not be loaded (artifact unavailable); candidate beats baseline "
            "at all key horizons (h1, h24, h48), promoted to restore a usable champion"
        )

    improvements_vs_champion = {
        h: relative_improvement(champion_mae_by_key_horizon[h], mae_by_key_horizon[h]) for h in key_horizons
    }
    failing_champion = [
        h for h in key_horizons if improvements_vs_champion[h] < settings.min_improvement_vs_champion
    ]
    if failing_champion:
        details = ", ".join(
            f"h={h}h mae={mae_by_key_horizon[h]:.4f} champion_mae={champion_mae_by_key_horizon[h]:.4f} "
            f"(actual={improvements_vs_champion[h]:.1%})"
            for h in failing_champion
        )
        return False, (
            f"candidate does not beat champion by the required {settings.min_improvement_vs_champion:.1%} "
            f"at key horizon(s) {failing_champion} ({details})"
        )

    return True, (
        f"candidate mae_h1={mae_by_key_horizon[1]:.4f} beats champion at all key horizons (h1, h24, h48) "
        f"by the required {settings.min_improvement_vs_champion:.1%}"
    )
