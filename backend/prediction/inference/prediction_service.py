from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

import mlflow
import numpy as np
import pandas as pd
from mlflow.tracking import MlflowClient

from prediction.config import PredictionSettings, get_settings
from prediction.dataset.dataset import MAX_HORIZON_HOURS
from prediction.inference.feature_builder import build_latest_features
from prediction.registry import model_registry as registry
from prediction.repository.prediction_repository import record_prediction, record_predictions

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


@dataclass(frozen=True)
class ForecastPointResult:
    horizon_hours: int
    target_timestamp: pd.Timestamp
    predicted_consumption_kw: float


@dataclass(frozen=True)
class ForecastResult:
    site_id: str
    generated_at: pd.Timestamp
    base_timestamp: pd.Timestamp
    horizon_hours: int
    model_version: str
    points: list[ForecastPointResult]


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

    def _predict_all_horizons(self, site_id: str) -> tuple[np.ndarray, pd.Timestamp, str]:
        """
        Charge le champion, construit les features du dernier point exploitable
        du site (`base_timestamp`), et prédit en **un seul appel** les 168
        horizons (modèle multi-output direct, cf. training/pipeline.py -- pas
        de boucle récursive, pas de réinjection des prédictions précédentes).
        Renvoie un tableau 1D de `MAX_HORIZON_HOURS` valeurs, indexé horizon-1
        (predictions[0] = T+1h, ..., predictions[167] = T+168h).
        """
        model, version = self._cache.get(self._client)
        X, base_timestamp = build_latest_features(site_id)
        predictions = np.asarray(model.predict(X))[0]
        return predictions, base_timestamp, version

    def predict(self, site_id: str, persist: bool = True) -> PredictionResult:
        """Prédiction T+1h (conservée pour compatibilité de `/prediction`) --
        équivalente au premier point d'un `forecast(site_id, hours=1)`."""
        predictions, base_timestamp, version = self._predict_all_horizons(site_id)
        predicted_consumption_kw = float(predictions[0])
        target_timestamp = base_timestamp + timedelta(hours=1)
        prediction_timestamp = pd.Timestamp.now(tz="UTC")

        if persist:
            try:
                record_prediction(
                    site_id=site_id,
                    predicted_for=target_timestamp,
                    predicted_consumption_kw=predicted_consumption_kw,
                    model_version=version,
                    horizon_hours=1,
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

    def forecast(self, site_id: str, hours: int, persist: bool = True) -> ForecastResult:
        """
        Courbe horaire T+1h..T+`hours`h (1 <= hours <= 168), à partir du même
        modèle multi-output et du même point d'ancrage que `predict()`. Chaque
        horizon est une sortie directe du modèle (pas de boucle, pas de
        réinjection des prédictions précédentes) : l'erreur ne se propage pas
        d'un horizon à l'autre -- cf. MACHINE_LEARNING_IMPLEMENTATION.md
        §Forecast multi-horizon.

        `base_timestamp` (dernière mesure réellement utilisée pour construire
        les features) et `generated_at` (horloge système, instant de l'appel)
        sont volontairement distincts : avec un dataset simulé/historique,
        `base_timestamp` peut être postérieur à l'horloge système (§5 du besoin) --
        les `target_timestamp` sont toujours calculés depuis `base_timestamp`,
        jamais depuis `generated_at`.
        """
        if not (1 <= hours <= MAX_HORIZON_HOURS):
            raise ValueError(f"hours must be between 1 and {MAX_HORIZON_HOURS}, got {hours}")

        predictions, base_timestamp, version = self._predict_all_horizons(site_id)
        generated_at = pd.Timestamp.now(tz="UTC")

        points = [
            ForecastPointResult(
                horizon_hours=horizon_hours,
                target_timestamp=base_timestamp + timedelta(hours=horizon_hours),
                predicted_consumption_kw=float(predictions[horizon_hours - 1]),
            )
            for horizon_hours in range(1, hours + 1)
        ]

        if persist:
            try:
                record_predictions(
                    [
                        {
                            "site_id": site_id,
                            "predicted_for": point.target_timestamp,
                            "predicted_consumption_kw": point.predicted_consumption_kw,
                            "model_version": version,
                            "horizon_hours": point.horizon_hours,
                        }
                        for point in points
                    ]
                )
            except Exception:
                logger.exception(
                    "failed to persist forecast",
                    extra={
                        "event": "forecast_persistence_failed",
                        "site_id": site_id,
                        "horizon_hours": hours,
                    },
                )

        logger.info(
            "forecast executed",
            extra={
                "event": "forecast_executed",
                "site_id": site_id,
                "model_name": self._settings.mlflow_model_name,
                "model_version": version,
                "model_alias": "champion",
                "horizon_hours": hours,
                "n_points": len(points),
            },
        )

        return ForecastResult(
            site_id=site_id,
            generated_at=generated_at,
            base_timestamp=base_timestamp,
            horizon_hours=hours,
            model_version=version,
            points=points,
        )
