"""Accès au modèle de prédiction de consommation.

Ce module isole le chargement du modèle entraîné (registre MLflow) du reste de
l'API. Tant qu'aucun modèle exploitable n'est publié, `load_consumption_model`
renvoie `None` : l'endpoint `/api/v1/backend/prediction/{site_id}` répond alors
503 avec un message explicite.

Quand un modèle sera disponible, seule l'implémentation de
`load_consumption_model` change -- chargement direct via `mlflow` ou appel à un
service de scoring dédié. Le contrat exposé (un objet `ConsumptionModel`) et le
reste de la chaîne (`PredictionService`, controller) restent identiques, et la
dépendance `mlflow` n'est ajoutée à l'API que le jour où elle est réellement
utilisée.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

MODEL_NAME = "consumption-predictor"


@dataclass(frozen=True)
class ConsumptionForecast:
    """Résultat brut d'une prédiction pour un site."""

    predicted_consumption_kw: float
    prediction_date: datetime


@runtime_checkable
class ConsumptionModel(Protocol):
    """Modèle chargé, prêt à produire une prédiction pour un site."""

    name: str
    version: str | None

    def predict_next(self, site_id: str) -> ConsumptionForecast: ...


def load_consumption_model() -> ConsumptionModel | None:
    """Retourne le modèle courant, ou `None` si aucun n'est disponible.

    Point de branchement MLflow : implémentation à fournir quand
    l'entraînement publiera un modèle exploitable dans le registre.
    """

    return None
