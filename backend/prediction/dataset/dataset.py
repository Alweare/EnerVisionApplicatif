"""
Constitution et découpage du jeu d'entraînement (EN-263), étendu au forecast
multi-horizon (T+1h à T+48h).

Cible = consommation à T+1h..T+48h (décalées dans le futur : prédire le
présent ne sert à rien). Split strictement chronologique, jamais aléatoire :
en prod on prédit toujours vers le futur, s'entraîner sur des dates
postérieures au test fausse l'évaluation.

`TARGET_COLUMN` ("target") reste la cible T+1h historique (alias de
`target_h1`), conservée pour compatibilité avec le code/tests existants.
`MULTI_HORIZON_TARGET_COLUMNS` porte les 48 cibles T+1h..T+48h utilisées par
le modèle de forecast (un seul régresseur multi-output, cf. training/pipeline.py).
"""

from __future__ import annotations

import pandas as pd

from prediction.features.time_features import ROWS_PER_HOUR, add_time_features
from prediction.repository.measurement_repository import get_measurements

# Features "consommation passée" : lags + moyennes glissantes, calculées par
# site à partir de l'historique brut (features/time_features.add_time_features).
CONSUMPTION_FEATURE_COLUMNS = ["consumption_kw", "lag_10min","lag_30min","lag_1h", "lag_24h", "lag_168h", "rolling_mean_24h", "rolling_mean_168h"]
# Features calendaires : déterministes depuis measurement_date, pas de fuite,
# pas d'historique requis. Ajoutées pour donner un signal de saisonnalité
# journalière/hebdomadaire nécessaire au-delà de quelques heures d'horizon.
# hour_sin/hour_cos/day_sin/day_cos encodent hour_of_day/day_of_week sous
# forme cyclique (23h proche de 0h, dimanche proche de lundi) -- une
# LinearRegression ne peut pas capter cette proximité depuis la valeur brute.
CALENDAR_FEATURE_COLUMNS = [
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "day_sin",
    "day_cos",
]
FEATURE_COLUMNS = CONSUMPTION_FEATURE_COLUMNS + CALENDAR_FEATURE_COLUMNS

# Features participant au calcul de drift (PSI). Les features calendaires sont
# volontairement exclues : leur distribution est mécaniquement stable (le
# calendrier boucle toujours de la même façon), un PSI dessus ne mesurerait
# qu'un artefact d'échantillonnage de la fenêtre d'entraînement, pas une vraie
# dérive du signal de consommation -- cf. MACHINE_LEARNING_IMPLEMENTATION.md.
DRIFT_FEATURE_COLUMNS = CONSUMPTION_FEATURE_COLUMNS

TARGET_COLUMN = "target"

# Horizon 1 h, décalage par nombre de lignes comme les lags EN-37. Conservé
# pour compatibilité (alias de la cible T+1h).
HORIZON_ROWS = ROWS_PER_HOUR

# Forecast multi-horizon : granularité 1 h, horizon 1..48 h (2 jours).
MAX_HORIZON_HOURS = 48
HORIZONS_HOURS = list(range(1, MAX_HORIZON_HOURS + 1))

# Horizons clés utilisés pour l'évaluation et la promotion.
KEY_HORIZONS_HOURS = (1, 24, 48)
TARGET_COLUMN_PREFIX = "target_h"
MULTI_HORIZON_TARGET_COLUMNS = [f"{TARGET_COLUMN_PREFIX}{h}" for h in HORIZONS_HOURS]

# 80 % des dates les plus anciennes en train. Cutoff global : suppose des
# historiques comparables entre sites, à revoir en split par site sinon.
DEFAULT_CUTOFF_RATIO = 0.8

DEFAULT_TRAIN_RATIO = 0.7
DEFAULT_VALIDATION_RATIO = 0.15


class NotEnoughDataError(Exception):
    """Pas assez d'historique exploitable pour constituer un jeu d'entraînement."""


def build_dataset() -> pd.DataFrame:
    """
    Ajoute une cible par horizon (`target_h1`..`target_h48`) = `consumption_kw`
    décalée de h heures par site. `TARGET_COLUMN` ("target") reste un alias de
    `target_h1`, pour compatibilité.

    Fin de série (pas de futur connu au-delà de l'historique disponible) et
    lignes forward-fillées neutralisées -> cibles NaN, retirées au découpage.
    """
    df = add_time_features(get_measurements())
    grouped_consumption = df.groupby("site_id")["consumption_kw"]
    # Construites en un DataFrame séparé puis concaténées en une fois : 48
    # `df[col] = ...` répétés fragmenteraient le DataFrame (avertissement
    # pandas), sans changer le résultat.
    targets = pd.concat(
        {
            f"{TARGET_COLUMN_PREFIX}{horizon_hours}": grouped_consumption.shift(-horizon_hours * ROWS_PER_HOUR)
            for horizon_hours in HORIZONS_HOURS
        },
        axis=1,
    )
    df = pd.concat([df, targets], axis=1)
    df[TARGET_COLUMN] = df[f"{TARGET_COLUMN_PREFIX}1"]
    return df


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])
    return df.sort_values("measurement_date")


def clean_multi_horizon_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    Comme `clean_dataset`, mais exige les 48 cibles (une ligne n'est
    exploitable pour l'entraînement multi-output que si son futur est connu
    jusqu'à T+48h). Réduit la fenêtre d'entraînement utilisable aux lignes
    dont les 2 jours suivants sont déjà observés -- attendu, pas un bug.
    """
    df = df.dropna(subset=FEATURE_COLUMNS + MULTI_HORIZON_TARGET_COLUMNS)
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


def split_train_val_test_multi_horizon(
    df: pd.DataFrame,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    validation_ratio: float = DEFAULT_VALIDATION_RATIO,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Comme `split_train_val_test`, mais nettoie via `clean_multi_horizon_dataset`
    (48 cibles requises). C'est le split réellement utilisé par le pipeline
    d'entraînement du modèle de forecast (training/pipeline.py).
    """
    train, validation, test = _split_by_cutoffs(
        clean_multi_horizon_dataset(df), [train_ratio, train_ratio + validation_ratio]
    )
    return train, validation, test
