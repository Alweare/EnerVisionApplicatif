"""
Constitution et découpage du jeu d'entraînement (EN-263).

Cible = consommation à T+1h (décalée dans le futur : prédire le présent ne sert
à rien). Split strictement chronologique, jamais aléatoire : en prod on prédit
toujours vers le futur, s'entraîner sur des dates postérieures au test fausse
l'évaluation.
"""

from __future__ import annotations

import pandas as pd

from prediction.features.time_features import ROWS_PER_HOUR, add_time_features
from prediction.repository.measurement_repository import get_measurements

FEATURE_COLUMNS = ["lag_1h", "lag_24h", "rolling_mean_24h"]
TARGET_COLUMN = "target"

# Horizon 1 h, décalage par nombre de lignes comme les lags EN-37.
HORIZON_ROWS = ROWS_PER_HOUR

# 80 % des dates les plus anciennes en train. Cutoff global : suppose des
# historiques comparables entre sites, à revoir en split par site sinon.
DEFAULT_CUTOFF_RATIO = 0.8


class NotEnoughDataError(Exception):
    """Pas assez d'historique exploitable pour constituer un jeu d'entraînement."""


def build_dataset() -> pd.DataFrame:
    """
    Cible = `consumption_kw` décalée d'1 h par site.

    Fin de série (pas de futur connu) et lignes forward-fillées neutralisées par
    cible NaN, retirée au découpage.
    """
    df = add_time_features(get_measurements())
    df[TARGET_COLUMN] = df.groupby("site_id")["consumption_kw"].shift(-HORIZON_ROWS)
    return df


def _split_by_cutoff(
    df: pd.DataFrame, cutoff_ratio: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Découpe `df` en (train, test) sur une date de coupure.

    Retire les lignes à feature ou cible manquante (aucune imputation), trie par
    date, coupe au rang `cutoff_ratio` : avant -> train, à partir de -> test.
    """
    df = df.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])
    df = df.sort_values("measurement_date")

    if len(df) < 2:
        raise NotEnoughDataError(
            f"{len(df)} ligne(s) exploitable(s) après nettoyage, minimum 2"
        )

    cutoff_index = min(int(len(df) * cutoff_ratio), len(df) - 1)
    cutoff_date = df.iloc[cutoff_index]["measurement_date"]

    train = df[df["measurement_date"] < cutoff_date]
    test = df[df["measurement_date"] >= cutoff_date]

    if train.empty or test.empty:
        raise NotEnoughDataError(
            f"découpage vide (train={len(train)}, test={len(test)}) : "
            "historique trop court ou concentré sur une seule date"
        )

    return train, test


def split_train_test(
    df: pd.DataFrame, cutoff_ratio: float = DEFAULT_CUTOFF_RATIO
):
    """
    (X_train, X_test, y_train, y_test) à partir de `build_dataset()`, prêt pour
    `model.fit`. `X_*` ne contient que `FEATURE_COLUMNS`.
    """
    train, test = _split_by_cutoff(df, cutoff_ratio)
    return (
        train[FEATURE_COLUMNS],
        test[FEATURE_COLUMNS],
        train[TARGET_COLUMN],
        test[TARGET_COLUMN],
    )
