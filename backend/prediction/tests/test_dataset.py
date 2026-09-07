"""
Tests de la constitution / du découpage du jeu d'entraînement (EN-263).

Comme pour EN-37, tout tourne sur des DataFrames synthétiques -- aucune base
réelle nécessaire.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from prediction.dataset.dataset import (
    FEATURE_COLUMNS,
    HORIZON_ROWS,
    TARGET_COLUMN,
    NotEnoughDataError,
    _split_by_cutoff,
    build_dataset,
    split_train_test,
)

START = datetime(2026, 1, 1)


def _dataset_frame(n: int = 1000) -> pd.DataFrame:
    """Jeu déjà enrichi : features + cible renseignées, une ligne par minute."""
    return pd.DataFrame(
        {
            "site_id": "SITE_A",
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "lag_1h": [float(i) for i in range(n)],
            "lag_24h": [float(i) for i in range(n)],
            "rolling_mean_24h": [float(i) for i in range(n)],
            TARGET_COLUMN: [float(i) for i in range(n)],
        }
    )


def _raw_frame(sites, n: int) -> pd.DataFrame:
    """Ce que renvoie get_measurements : mesures brutes, lectures complètes."""
    rows = []
    for s_idx, site in enumerate(sites):
        for i in range(n):
            rows.append(
                {
                    "site_id": site,
                    "measurement_date": START + timedelta(minutes=i),
                    "consumption_kw": 100.0 + i + s_idx * 1000.0,
                    "data_quality": "good",
                    "null_reason": None,
                }
            )
    return pd.DataFrame(rows)


# --- Critère : découpage chronologique, jamais aléatoire ------------------

def test_split_respects_chronological_order():
    train, test = _split_by_cutoff(_dataset_frame(1000), 0.8)
    assert train["measurement_date"].max() < test["measurement_date"].min()


def test_no_test_date_precedes_a_train_date():
    train, test = _split_by_cutoff(_dataset_frame(1000), 0.8)
    assert test["measurement_date"].min() >= train["measurement_date"].max()


# --- Critère : aucune ligne à feature/cible manquante dans train ou test --

def test_missing_feature_or_target_rows_are_excluded():
    df = _dataset_frame(1000)
    df.loc[10:19, "lag_24h"] = np.nan       # 10 lignes : feature manquante
    df.loc[500, TARGET_COLUMN] = np.nan     # 1 ligne : cible manquante

    train, test = _split_by_cutoff(df, 0.8)
    kept = pd.concat([train, test])

    assert len(kept) == 1000 - 11
    assert not kept[FEATURE_COLUMNS + [TARGET_COLUMN]].isna().any().any()


# --- Critère : ratio 80/20 documenté ------------------------------------

def test_default_ratio_is_roughly_80_20():
    train, test = _split_by_cutoff(_dataset_frame(1000), 0.8)
    ratio = len(train) / (len(train) + len(test))
    assert abs(ratio - 0.8) < 0.02


# --- Cible = valeur future, par site ----------------------------------

def test_build_dataset_target_is_consumption_one_hour_later_per_site(monkeypatch):
    raw = _raw_frame(["SITE_A", "SITE_B"], n=200)
    monkeypatch.setattr("prediction.dataset.dataset.get_measurements", lambda: raw.copy())

    ds = build_dataset()
    a = ds[ds.site_id == "SITE_A"].reset_index(drop=True)

    # cible à T = consommation réelle à T + HORIZON_ROWS, même site
    assert a[TARGET_COLUMN].iloc[100] == a["consumption_kw"].iloc[100 + HORIZON_ROWS]
    # les HORIZON_ROWS dernières lignes du site n'ont pas de futur -> NaN
    assert a[TARGET_COLUMN].iloc[-HORIZON_ROWS:].isna().all()
    # pas de fuite entre sites : la dernière ligne de SITE_A ne récupère pas
    # une valeur de SITE_B
    assert pd.isna(a[TARGET_COLUMN].iloc[-1])


# --- Garde-fous : pas assez de données -------------------------------

def test_raises_when_dataset_too_small():
    with pytest.raises(NotEnoughDataError):
        _split_by_cutoff(_dataset_frame(1), 0.8)


def test_raises_when_all_rows_share_one_date():
    df = _dataset_frame(50)
    df["measurement_date"] = START
    with pytest.raises(NotEnoughDataError):
        _split_by_cutoff(df, 0.8)


# --- split_train_test : n'expose que les features ---------------------

def test_split_train_test_returns_only_feature_columns():
    X_train, X_test, y_train, y_test = split_train_test(_dataset_frame(1000))

    assert list(X_train.columns) == FEATURE_COLUMNS
    assert list(X_test.columns) == FEATURE_COLUMNS
    assert "site_id" not in X_train.columns
    assert "measurement_date" not in X_train.columns
    assert y_train.name == TARGET_COLUMN
    assert len(X_train) == len(y_train)
    assert len(X_test) == len(y_test)
