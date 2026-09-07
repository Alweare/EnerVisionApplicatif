"""
Constitution et découpage du jeu d'entraînement (EN-263).

À partir des mesures enrichies (EN-37), construit la cible -- la consommation
à T+1h -- et découpe train / test de façon **strictement chronologique**.

Pourquoi pas un split aléatoire : en production on prédit toujours vers le
futur. Un split aléatoire entraînerait le modèle sur des dates postérieures à
celles du test, situation qui n'arrive jamais en vrai -> évaluation trompeuse.

Pourquoi la cible est décalée dans le futur : prédire consumption_kw à
l'instant T ne sert à rien (la vraie mesure arrive de toute façon en direct
via l'ETL). La cible est donc la consommation HORIZON_ROWS lignes plus tard
-- le modèle apprend à anticiper, pas à reconstituer le présent.
"""

from __future__ import annotations

import pandas as pd

from prediction.features.time_features import ROWS_PER_HOUR, add_time_features
from prediction.repository.measurement_repository import get_measurements

FEATURE_COLUMNS = ["lag_1h", "lag_24h", "rolling_mean_24h"]
TARGET_COLUMN = "target"

# Horizon de prédiction : 1 h dans le futur. Décalage par nombre de lignes
# (1 mesure/minute), même limite que les lags d'EN-37 : approximatif si des
# minutes manquent en base.
HORIZON_ROWS = ROWS_PER_HOUR

# Ratio par défaut : 80 % des dates les plus anciennes -> entraînement, 20 %
# les plus récentes -> test. Cutoff global sur toute la table ; suppose des
# historiques comparables entre sites. À repasser en split par site si le
# volume par site devient très inégal.
DEFAULT_CUTOFF_RATIO = 0.8


class NotEnoughDataError(Exception):
    """Pas assez d'historique exploitable pour constituer un jeu d'entraînement."""


def build_dataset() -> pd.DataFrame:
    """
    Jeu de données complet : les features d'EN-37 + la colonne cible.

    La cible (`shift(-HORIZON_ROWS)` par site) est la consommation 1 h plus
    tard. Les dernières lignes de chaque site n'ont pas de futur connu -> cible
    NaN (retirées au découpage). Comme `consumption_kw` est déjà mise à NaN par
    EN-37 sur les lignes forward-fillées, la cible hérite de ces NaN : on
    n'entraîne jamais le modèle à prédire une valeur recopiée.
    """
    df = add_time_features(get_measurements())
    df[TARGET_COLUMN] = df.groupby("site_id")["consumption_kw"].shift(-HORIZON_ROWS)
    return df


def _split_by_cutoff(
    df: pd.DataFrame, cutoff_ratio: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Découpe `df` en (train, test) sur une date de coupure.

    Retire d'abord les lignes à features ou cible manquantes -- aucune
    imputation, choix de simplicité assumé. La date de coupure est celle de la
    ligne au rang `cutoff_ratio` une fois les lignes triées par date : tout ce
    qui est strictement avant va dans train, le reste dans test.
    """
    df = df.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])
    df = df.sort_values("measurement_date")

    if len(df) < 2:
        raise NotEnoughDataError(
            f"{len(df)} ligne(s) exploitable(s) après nettoyage -- il en faut "
            "au moins 2 pour un découpage train/test"
        )

    cutoff_index = min(int(len(df) * cutoff_ratio), len(df) - 1)
    cutoff_date = df.iloc[cutoff_index]["measurement_date"]

    train = df[df["measurement_date"] < cutoff_date]
    test = df[df["measurement_date"] >= cutoff_date]

    if train.empty or test.empty:
        raise NotEnoughDataError(
            f"le découpage chronologique laisse un jeu vide "
            f"(train={len(train)}, test={len(test)}) -- historique trop court "
            "ou concentré sur une seule date"
        )

    return train, test


def split_train_test(
    df: pd.DataFrame, cutoff_ratio: float = DEFAULT_CUTOFF_RATIO
):
    """
    (X_train, X_test, y_train, y_test) à partir du jeu de `build_dataset()`.

    Découpage strictement chronologique (cf. `_split_by_cutoff`). `X_*` ne
    contient que `FEATURE_COLUMNS` : ni `site_id` ni `measurement_date` ne sont
    des entrées du modèle. Alimente directement `model.fit(X_train, y_train)`
    (EN-39).
    """
    train, test = _split_by_cutoff(df, cutoff_ratio)
    return (
        train[FEATURE_COLUMNS],
        test[FEATURE_COLUMNS],
        train[TARGET_COLUMN],
        test[TARGET_COLUMN],
    )
