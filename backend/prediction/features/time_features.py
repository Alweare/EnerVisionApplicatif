"""
Feature engineering séries temporelles pour la prédiction de pics (EN-37).

Transforme l'historique brut (une mesure/minute/site) en colonnes exploitables
par la régression : consommation il y a 1 h, il y a 24 h, moyenne glissante 24 h.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ETL = 1 mesure/minute : un lag "horaire" décale d'un nombre de lignes.
ROWS_PER_HOUR = 60
ROWS_PER_DAY = 24 * ROWS_PER_HOUR

# null_reason pour lesquels consumption_kw a été recopiée par le forward-fill
# de l'ETL (donc non fiable). Les autres pannes laissent la conso intacte.
CONSUMPTION_TAINTING_REASONS = frozenset(
    {"consumption_sensor_failure", "network_loss"}
)


def _consumption_is_tainted(null_reason) -> bool:
    """True si consumption_kw de la ligne est une recopie du forward-fill."""
    if null_reason is None:
        return False
    return any(r in CONSUMPTION_TAINTING_REASONS for r in null_reason)


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ajoute lag_1h, lag_24h et rolling_mean_24h, calculés par site.

    Les lags valent NaN quand l'historique est trop court (jamais une valeur
    inventée). rolling_mean_24h applique shift(1) avant rolling pour ne jamais
    inclure la valeur de T -- sinon fuite de données. Décalage par nombre de
    lignes (1 mesure/minute), pas par temps réel : approximatif si des minutes
    manquent en base.
    """
    df = (
        df.sort_values(["site_id", "measurement_date"])
        .reset_index(drop=True)
        .copy()
    )

    tainted = df["null_reason"].apply(_consumption_is_tainted)
    df.loc[tainted, "consumption_kw"] = np.nan

    grouped = df.groupby("site_id")["consumption_kw"]
    df["lag_1h"] = grouped.shift(ROWS_PER_HOUR)
    df["lag_24h"] = grouped.shift(ROWS_PER_DAY)

    # shift(1) avant rolling : la fenêtre s'arrête à T-1, jamais T lui-même.
    df["rolling_mean_24h"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=ROWS_PER_DAY, min_periods=1).mean()
    )

    return df
