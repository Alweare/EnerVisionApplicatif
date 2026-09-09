from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prediction.features.time_features import CONSUMPTION_TAINTING_REASONS
from shared.database import engine as default_engine

_INSERT_QUERY = """
    INSERT INTO ener.prediction (site_id, predicted_for, predicted_consumption_kw, model_version, horizon_hours)
    VALUES (:site_id, :predicted_for, :predicted_consumption_kw, :model_version, :horizon_hours)
"""

# horizon_hours (migration V01_10) distingue les prédictions par horizon : sans
# ce filtre, un forecast 48h (jusqu'à 48 lignes/appel) noierait les
# prédictions T+1h et fausserait la comparaison à la MAE de référence (calculée
# à T+1h, cf. training/pipeline.py).
_MATCHED_QUERY = """
    SELECT p.site_id, p.predicted_for, p.predicted_consumption_kw, p.horizon_hours,
           m.consumption_kw, m.null_reason
    FROM ener.prediction p
    JOIN ener.measurement m
      ON m.site_id = p.site_id AND m.measurement_date = p.predicted_for
    WHERE p.model_version = :model_version AND p.horizon_hours = :horizon_hours
"""


def record_prediction(
    site_id: str,
    predicted_for: datetime,
    predicted_consumption_kw: float,
    model_version: str,
    horizon_hours: int,
    engine: Engine = default_engine,
) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(_INSERT_QUERY),
            {
                "site_id": site_id,
                "predicted_for": predicted_for,
                "predicted_consumption_kw": predicted_consumption_kw,
                "model_version": model_version,
                "horizon_hours": horizon_hours,
            },
        )


def record_predictions(rows: list[dict], engine: Engine = default_engine) -> None:
    """
    Insertion en lot (un forecast peut produire jusqu'à 48 lignes en un seul
    appel) : une seule transaction plutôt que 48 allers-retours séparés.
    Chaque `row` a les mêmes clés que les paramètres de `record_prediction`.
    """
    if not rows:
        return
    with engine.begin() as connection:
        connection.execute(text(_INSERT_QUERY), rows)


def _consumption_is_tainted(null_reason) -> bool:
    if not null_reason:
        return False
    return any(reason in CONSUMPTION_TAINTING_REASONS for reason in null_reason)


def get_matched_predictions(
    model_version: str, horizon_hours: int = 1, engine: Engine = default_engine
) -> pd.DataFrame:
    """
    Prédictions passées dont la mesure réelle est désormais connue, filtrées
    sur un seul horizon (par défaut 1h, l'horizon de référence historique du
    champion -- cf. commentaire sur `_MATCHED_QUERY`).
    """
    df = pd.read_sql(
        text(_MATCHED_QUERY),
        engine,
        params={"model_version": model_version, "horizon_hours": horizon_hours},
    )
    if df.empty:
        return df

    tainted = df["null_reason"].apply(_consumption_is_tainted)
    return df.loc[~tainted].dropna(subset=["consumption_kw", "predicted_consumption_kw"]).reset_index(drop=True)
