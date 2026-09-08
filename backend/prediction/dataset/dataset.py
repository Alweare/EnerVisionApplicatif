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

DEFAULT_TRAIN_RATIO = 0.7
DEFAULT_VALIDATION_RATIO = 0.15


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


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])
    return df.sort_values("measurement_date")


def _split_by_cutoffs(
    df: pd.DataFrame, cumulative_ratios: list[float]
) -> list[pd.DataFrame]:
    if len(df) < len(cumulative_ratios) + 1:
        raise NotEnoughDataError(
            f"{len(df)} ligne(s) exploitable(s) après nettoyage, minimum "
            f"{len(cumulative_ratios) + 1}"
        )

    cutoff_dates = [
        df.iloc[min(int(len(df) * ratio), len(df) - 1)]["measurement_date"]
        for ratio in cumulative_ratios
    ]

    bounds = [None, *cutoff_dates, None]
    slices = []
    for lower, upper in zip(bounds[:-1], bounds[1:]):
        chunk = df
        if lower is not None:
            chunk = chunk[chunk["measurement_date"] >= lower]
        if upper is not None:
            chunk = chunk[chunk["measurement_date"] < upper]
        slices.append(chunk)

    if any(chunk.empty for chunk in slices):
        sizes = [len(chunk) for chunk in slices]
        raise NotEnoughDataError(
            f"découpage vide (tailles={sizes}) : historique trop court ou "
            "concentré sur une seule date"
        )

    return slices


def _split_by_cutoff(
    df: pd.DataFrame, cutoff_ratio: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train, test = _split_by_cutoffs(clean_dataset(df), [cutoff_ratio])
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


def split_train_val_test(
    df: pd.DataFrame,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    validation_ratio: float = DEFAULT_VALIDATION_RATIO,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    train, validation, test = _split_by_cutoffs(
        clean_dataset(df), [train_ratio, train_ratio + validation_ratio]
    )
    return train, validation, test
