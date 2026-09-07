"""
Extraction des mesures pour le feature engineering (EN-37).

Renvoie un DataFrame trié par site puis date croissante -- ordre indispensable
pour tout calcul de lag ou de moyenne glissante en aval.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from shared.database import engine

# data_quality / null_reason : requis par add_time_features (neutralisation des
# consos recopiées) et par l'étape d'entraînement (exclusion des lignes
# dégradées comme cible).
_BASE_QUERY = """
    SELECT site_id, measurement_date, consumption_kw, data_quality, null_reason
    FROM ener.measurement
"""


def get_measurements(site_id: str | None = None) -> pd.DataFrame:
    """Mesures depuis Postgres, triées par site_id puis measurement_date."""
    query = _BASE_QUERY
    params: dict[str, str] = {}

    if site_id:
        query += " WHERE site_id = :site_id"
        params["site_id"] = site_id

    query += " ORDER BY site_id, measurement_date"

    return pd.read_sql(text(query), engine, params=params)
