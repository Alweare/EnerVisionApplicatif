"""
Feature engineering séries temporelles pour la prédiction de pics (EN-37) et
pour le forecast multi-horizon (T+1h à T+48h).

Transforme l'historique brut (une mesure/minute/site) en colonnes exploitables
par la régression : consommation il y a 1 h, 24 h, 168 h (7 j), moyennes
glissantes 24 h / 168 h, et des features calendaires déterministes (dont un
encodage cyclique sin/cos de l'heure et du jour de la semaine).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Les mesures sont échantillonnées toutes les 10 minutes :
# 6 mesures représentent donc une heure.
ROWS_PER_HOUR = 6
# 24 heures × 6 mesures/h = 144 mesures.
ROWS_PER_DAY = 24 * ROWS_PER_HOUR
# 7 jours × 144 mesures/jour = 1008 mesures.
# Utilisé pour lag_168h et rolling_mean_168h afin de capter
# la saisonnalité hebdomadaire.
ROWS_PER_WEEK = 7 * ROWS_PER_DAY

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
    Ajoute lag_1h, lag_24h, lag_168h, rolling_mean_24h, rolling_mean_168h,
    les features calendaires (hour_of_day, day_of_week, is_weekend) et leur
    encodage cyclique (hour_sin, hour_cos, day_sin, day_cos), calculées par
    site.

    Les lags valent NaN quand l'historique est trop court (jamais une valeur
    inventée). Les rolling_mean_* appliquent shift(1) avant rolling pour ne
    jamais inclure la valeur de T -- sinon fuite de données. Décalage par
    nombre de lignes (1 mesure/minute), pas par temps réel : approximatif si
    des minutes manquent en base.

    Les features calendaires sont une fonction pure et déterministe de
    `measurement_date` (l'horodatage de la ligne T elle-même, jamais celui
    d'une cible future) : aucune fuite possible, aucun historique requis.
    """
    df = (
        df.sort_values(["site_id", "measurement_date"])
        .reset_index(drop=True)
        .copy()
    )

    df["consumption_tainted"] = (
        df["null_reason"]
        .apply(_consumption_is_tainted)
        .astype(int)
    )

    grouped = df.groupby("site_id")["consumption_kw"]
    df["lag_10min"] = grouped.shift(1)
    df["lag_30min"] = grouped.shift(3)
    df["lag_1h"] = grouped.shift(ROWS_PER_HOUR)
    df["lag_24h"] = grouped.shift(ROWS_PER_DAY)
    df["lag_168h"] = grouped.shift(ROWS_PER_WEEK)

    # shift(1) avant rolling : la fenêtre s'arrête à T-1, jamais T lui-même.
    df["rolling_mean_24h"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=ROWS_PER_DAY, min_periods=1).mean()
    )
    df["rolling_mean_168h"] = grouped.transform(
        lambda s: s.shift(1).rolling(window=ROWS_PER_WEEK, min_periods=1).mean()
    )

    measurement_date = pd.to_datetime(df["measurement_date"])
    df["hour_of_day"] = measurement_date.dt.hour
    df["day_of_week"] = measurement_date.dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)

    # Encodage cyclique : hour_of_day/day_of_week sont des échelles circulaires
    # (23h est proche de 0h, dimanche proche de lundi) qu'une LinearRegression
    # ne peut pas capter depuis une valeur entière brute -- sin/cos préservent
    # cette proximité. Toujours une fonction pure de measurement_date de la
    # ligne T elle-même : aucune fuite, aucun historique requis.
    df["hour_sin"] = np.sin(2 * np.pi * df["hour_of_day"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour_of_day"] / 24)

    df["day_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
    df["day_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)

    return df
