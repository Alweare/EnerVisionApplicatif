"""
Accès en lecture aux mesures pour le feature engineering (EN-37).

Renvoie un DataFrame pandas prêt à passer dans
prediction.features.time_features.add_time_features : trié par site puis par
date croissante. L'ordre chronologique est indispensable -- un lag ou une
moyenne glissante n'ont de sens que sur une série dans le bon ordre.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from core.database import engine

# data_quality et null_reason sont remontés pour que :
#  - add_time_features neutralise les consommations recopiées par forward-fill
#    (via null_reason) ;
#  - l'étape d'entraînement (EN-39) puisse exclure les lignes dégradées comme
#    cible sans refaire une requête.
_BASE_QUERY = """
    SELECT site_id, measurement_date, consumption_kw, data_quality, null_reason
    FROM ener.measurement
"""


def get_measurements(site_id: str | None = None) -> pd.DataFrame:
    """
    Récupère les mesures depuis Postgres, triées par site_id puis
    measurement_date croissante.

    site_id : si fourni, restreint à ce site ; sinon renvoie tous les sites
    (chacun reste une série indépendante grâce au tri et au groupby dans
    add_time_features).
    """
    query = _BASE_QUERY
    params: dict[str, str] = {}

    if site_id:
        query += " WHERE site_id = :site_id"
        params["site_id"] = site_id

    query += " ORDER BY site_id, measurement_date"

    return pd.read_sql(text(query), engine, params=params)
