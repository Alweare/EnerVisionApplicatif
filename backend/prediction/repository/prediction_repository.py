from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from prediction.features.time_features import CONSUMPTION_TAINTING_REASONS
from shared.database import engine as default_engine

_INSERT_QUERY = """
    INSERT INTO ener.prediction (site_id, predicted_for, predicted_consumption_kw, model_version)
    VALUES (:site_id, :predicted_for, :predicted_consumption_kw, :model_version)
"""

_MATCHED_QUERY = """
    SELECT p.site_id, p.predicted_for, p.predicted_consumption_kw,
           m.consumption_kw, m.null_reason
    FROM ener.prediction p
    JOIN ener.measurement m
      ON m.site_id = p.site_id AND m.measurement_date = p.predicted_for
    WHERE p.model_version = :model_version
"""


def record_prediction(
    site_id: str,
    predicted_for: datetime,
    predicted_consumption_kw: float,
    model_version: str,
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
            },
        )


def _consumption_is_tainted(null_reason) -> bool:
    if not null_reason:
        return False
    return any(reason in CONSUMPTION_TAINTING_REASONS for reason in null_reason)


def get_matched_predictions(model_version: str, engine: Engine = default_engine) -> pd.DataFrame:
    df = pd.read_sql(text(_MATCHED_QUERY), engine, params={"model_version": model_version})
    if df.empty:
        return df

    tainted = df["null_reason"].apply(_consumption_is_tainted)
    return df.loc[~tainted].dropna(subset=["consumption_kw", "predicted_consumption_kw"]).reset_index(drop=True)
