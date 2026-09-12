from __future__ import annotations

import json
import logging

import mlflow
from mlflow.artifacts import download_artifacts
from mlflow.entities.model_registry import ModelVersion
from mlflow.exceptions import MlflowException
from mlflow.tracking import MlflowClient

from prediction.config import CHALLENGER_ALIAS, CHAMPION_ALIAS

logger = logging.getLogger(__name__)

DRIFT_REFERENCE_ARTIFACT_PATH = "drift_reference.json"
TRAINING_CUTOFF_PARAM = "dataset_max_date"


class ChampionLoadError(Exception):
    def __init__(self, model_name: str, cause: Exception):
        self.model_name = model_name
        self.cause = cause
        super().__init__(
            f"Le modèle champion '{model_name}' (alias '{CHAMPION_ALIAS}') est enregistré "
            f"mais son artefact est inaccessible : {cause}"
        )


def get_model_version_by_alias(
    client: MlflowClient, model_name: str, alias: str
) -> ModelVersion | None:
    try:
        return client.get_model_version_by_alias(model_name, alias)
    except MlflowException:
        return None


def get_champion_version(client: MlflowClient, model_name: str) -> ModelVersion | None:
    return get_model_version_by_alias(client, model_name, CHAMPION_ALIAS)


def load_champion_model(model_name: str):
    try:
        return mlflow.sklearn.load_model(f"models:/{model_name}@{CHAMPION_ALIAS}")
    except MlflowException as error:
        raise ChampionLoadError(model_name, error) from error


def register_challenger(client: MlflowClient, model_name: str, model_uri: str) -> ModelVersion:
    model_version = mlflow.register_model(model_uri, model_name)
    client.set_registered_model_alias(model_name, CHALLENGER_ALIAS, model_version.version)
    client.set_model_version_tag(model_name, model_version.version, "candidate", "true")
    return client.get_model_version(model_name, model_version.version)


def _clear_challenger_alias(client: MlflowClient, model_name: str) -> None:
    try:
        client.delete_registered_model_alias(model_name, CHALLENGER_ALIAS)
    except MlflowException:
        pass


def promote_to_champion(client: MlflowClient, model_name: str, version: str, reason: str) -> None:
    client.set_registered_model_alias(model_name, CHAMPION_ALIAS, version)
    client.set_model_version_tag(model_name, version, "promoted", "true")
    client.set_model_version_tag(model_name, version, "rejected", "false")
    client.set_model_version_tag(model_name, version, "reason", reason)
    _clear_challenger_alias(client, model_name)
    logger.info(
        "model promoted",
        extra={
            "event": "model_promoted",
            "model_name": model_name,
            "model_version": version,
            "model_alias": CHAMPION_ALIAS,
            "reason": reason,
        },
    )


def reject_challenger(client: MlflowClient, model_name: str, version: str, reason: str) -> None:
    client.set_model_version_tag(model_name, version, "promoted", "false")
    client.set_model_version_tag(model_name, version, "rejected", "true")
    client.set_model_version_tag(model_name, version, "reason", reason)
    _clear_challenger_alias(client, model_name)
    logger.info(
        "candidate rejected",
        extra={
            "event": "candidate_rejected",
            "model_name": model_name,
            "model_version": version,
            "reason": reason,
        },
    )


def save_drift_reference(reference_stats: dict) -> None:
    mlflow.log_dict(reference_stats, DRIFT_REFERENCE_ARTIFACT_PATH)


def load_drift_reference(model_version: ModelVersion) -> dict | None:
    try:
        local_path = download_artifacts(
            run_id=model_version.run_id, artifact_path=DRIFT_REFERENCE_ARTIFACT_PATH
        )
    except (MlflowException, OSError):
        return None

    with open(local_path, encoding="utf-8") as handle:
        return json.load(handle)


def get_run_metric(client: MlflowClient, run_id: str, key: str) -> float | None:
    run = client.get_run(run_id)
    return run.data.metrics.get(key)


def get_run_param(client: MlflowClient, run_id: str, key: str) -> str | None:
    run = client.get_run(run_id)
    return run.data.params.get(key)


def count_runs_with_tag(client: MlflowClient, experiment_id: str, tag_key: str, tag_value: str) -> int:
    runs = client.search_runs(
        experiment_ids=[experiment_id],
        filter_string=f"tags.`{tag_key}` = '{tag_value}'",
        max_results=50000,
    )
    return len(runs)


def count_versions_with_tag(client: MlflowClient, model_name: str, tag_key: str, tag_value: str) -> int:
    versions = client.search_model_versions(f"name='{model_name}'")
    return sum(1 for version in versions if version.tags.get(tag_key) == tag_value)
