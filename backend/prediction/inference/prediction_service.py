from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import mlflow
import pandas as pd
from mlflow.tracking import MlflowClient

from prediction.config import PredictionSettings, get_settings
from prediction.dataset.dataset import HORIZON_ROWS
from prediction.inference.feature_builder import build_latest_features
from prediction.registry import model_registry as registry
from prediction.repository.prediction_repository import record_prediction

logger = logging.getLogger(__name__)


class NoChampionModelError(Exception):
    def __init__(self, model_name: str):
        self.model_name = model_name
        super().__init__(f"Aucun modèle champion disponible pour '{model_name}'")


@dataclass(frozen=True)
class PredictionResult:
    site_id: str
    prediction_timestamp: pd.Timestamp
    target_timestamp: pd.Timestamp
    predicted_consumption_kw: float
    model_version: str


class ChampionModelCache:
    def __init__(self, model_name: str):
        self._model_name = model_name
        self._version: str | None = None
        self._model = None

    def get(self, client: MlflowClient):
        current = registry.get_champion_version(client, self._model_name)
        if current is None:
            raise NoChampionModelError(self._model_name)

        if str(current.version) != self._version:
            logger.info(
                "loading champion model",
                extra={
                    "event": "champion_model_loaded",
                    "model_name": self._model_name,
                    "model_alias": "champion",
                    "model_version": current.version,
                },
            )
            self._model = registry.load_champion_model(self._model_name)
            self._version = str(current.version)

        return self._model, self._version


class PredictionService:
    def __init__(
        self,
        settings: PredictionSettings | None = None,
        cache: ChampionModelCache | None = None,
    ):
        self._settings = settings or get_settings()
        mlflow.set_tracking_uri(self._settings.mlflow_tracking_uri)
        self._client = MlflowClient()
        self._cache = cache or ChampionModelCache(self._settings.mlflow_model_name)

    def predict(self, site_id: str, persist: bool = True) -> PredictionResult:
        model, version = self._cache.get(self._client)
        X, measurement_date = build_latest_features(site_id)

        predicted_consumption_kw = float(model.predict(X)[0])
        target_timestamp = measurement_date + timedelta(minutes=HORIZON_ROWS)
        prediction_timestamp = pd.Timestamp.now(tz="UTC")

        if persist:
            try:
                record_prediction(
                    site_id=site_id,
                    predicted_for=target_timestamp,
                    predicted_consumption_kw=predicted_consumption_kw,
                    model_version=version,
                )
            except Exception:
                logger.exception(
                    "failed to persist prediction",
                    extra={"event": "prediction_persistence_failed", "site_id": site_id},
                )

        logger.info(
            "prediction executed",
            extra={
                "event": "prediction_executed",
                "site_id": site_id,
                "model_name": self._settings.mlflow_model_name,
                "model_version": version,
                "model_alias": "champion",
                "prediction": predicted_consumption_kw,
            },
        )

        return PredictionResult(
            site_id=site_id,
            prediction_timestamp=prediction_timestamp,
            target_timestamp=target_timestamp,
            predicted_consumption_kw=predicted_consumption_kw,
            model_version=version,
        )
