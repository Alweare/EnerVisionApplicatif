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
    CALENDAR_FEATURE_COLUMNS,
    DRIFT_FEATURE_COLUMNS,
    FEATURE_COLUMNS,
    HORIZON_ROWS,
    HORIZONS_HOURS,
    MULTI_HORIZON_TARGET_COLUMNS,
    TARGET_COLUMN,
    NotEnoughDataError,
    _split_by_cutoff,
    build_dataset,
    clean_dataset,
    clean_multi_horizon_dataset,
    split_train_test,
    split_train_val_test,
    split_train_val_test_multi_horizon,
)

START = datetime(2026, 1, 1)


def _dataset_frame(n: int = 1000) -> pd.DataFrame:
    """Jeu déjà enrichi : features + cible T+1h renseignées, une ligne par minute."""
    columns = {
        "site_id": "SITE_A",
        "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
        "lag_1h": [float(i) for i in range(n)],
        "lag_24h": [float(i) for i in range(n)],
        "lag_168h": [float(i) for i in range(n)],
        "rolling_mean_24h": [float(i) for i in range(n)],
        "rolling_mean_168h": [float(i) for i in range(n)],
        "hour_of_day": [i % 24 for i in range(n)],
        "day_of_week": [i % 7 for i in range(n)],
        "is_weekend": [int(i % 7 >= 5) for i in range(n)],
        "hour_sin": [np.sin(2 * np.pi * (i % 24) / 24) for i in range(n)],
        "hour_cos": [np.cos(2 * np.pi * (i % 24) / 24) for i in range(n)],
        "day_sin": [np.sin(2 * np.pi * (i % 7) / 7) for i in range(n)],
        "day_cos": [np.cos(2 * np.pi * (i % 7) / 7) for i in range(n)],
        TARGET_COLUMN: [float(i) for i in range(n)],
    }
    return pd.DataFrame(columns)


def _multi_horizon_dataset_frame(n: int = 1000) -> pd.DataFrame:
    """Comme `_dataset_frame`, en ajoutant les 48 cibles multi-horizon."""
    df = _dataset_frame(n)
    for horizon_hours in HORIZONS_HOURS:
        df[f"target_h{horizon_hours}"] = [float(i) for i in range(n)]
    return df


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


def test_split_train_val_test_is_chronological_and_disjoint():
    train, validation, test = split_train_val_test(_dataset_frame(1000))

    assert train["measurement_date"].max() < validation["measurement_date"].min()
    assert validation["measurement_date"].max() < test["measurement_date"].min()


def test_split_train_val_test_respects_default_ratios():
    train, validation, test = split_train_val_test(_dataset_frame(1000))
    total = len(train) + len(validation) + len(test)

    assert abs(len(train) / total - 0.7) < 0.02
    assert abs(len(validation) / total - 0.15) < 0.02
    assert abs(len(test) / total - 0.15) < 0.02


def test_split_train_val_test_keeps_all_columns_for_downstream_use():
    train, validation, test = split_train_val_test(_dataset_frame(1000))

    for chunk in (train, validation, test):
        for column in FEATURE_COLUMNS + [TARGET_COLUMN, "site_id", "measurement_date"]:
            assert column in chunk.columns


def test_split_train_val_test_raises_when_dataset_too_small():
    with pytest.raises(NotEnoughDataError):
        split_train_val_test(_dataset_frame(2))


def test_split_train_val_test_no_row_used_in_more_than_one_split():
    df = _dataset_frame(1000)
    train, validation, test = split_train_val_test(df)

    train_dates = set(train["measurement_date"])
    validation_dates = set(validation["measurement_date"])
    test_dates = set(test["measurement_date"])

    assert not (train_dates & validation_dates)
    assert not (validation_dates & test_dates)
    assert not (train_dates & test_dates)
    assert len(train) + len(validation) + len(test) == len(df)


def test_clean_dataset_drops_missing_feature_or_target_and_sorts():
    df = _dataset_frame(100)
    df.loc[5, "lag_1h"] = np.nan
    shuffled = df.sample(frac=1, random_state=0)

    cleaned = clean_dataset(shuffled)

    assert len(cleaned) == 99
    assert cleaned["measurement_date"].is_monotonic_increasing


# --- Forecast multi-horizon : 48 cibles -------------------------------------


def test_build_dataset_creates_one_target_column_per_horizon(monkeypatch):
    n = 400
    raw = pd.DataFrame(
        {
            "site_id": "SITE_A",
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "consumption_kw": [float(i) for i in range(n)],
            "data_quality": "good",
            "null_reason": None,
        }
    )
    monkeypatch.setattr("prediction.dataset.dataset.get_measurements", lambda: raw.copy())

    ds = build_dataset()

    assert set(MULTI_HORIZON_TARGET_COLUMNS) <= set(ds.columns)
    assert len(MULTI_HORIZON_TARGET_COLUMNS) == 48
    # target_h1 == TARGET_COLUMN (alias de compatibilité).
    pd.testing.assert_series_equal(
        ds["target_h1"], ds[TARGET_COLUMN], check_names=False
    )


def test_multi_horizon_targets_use_the_correct_shift_per_horizon(monkeypatch):
    n = 500
    raw = pd.DataFrame(
        {
            "site_id": "SITE_A",
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "consumption_kw": [float(i) for i in range(n)],
            "data_quality": "good",
            "null_reason": None,
        }
    )
    monkeypatch.setattr("prediction.dataset.dataset.get_measurements", lambda: raw.copy())

    ds = build_dataset()

    # target_h2 à la ligne 10 = consommation réelle 2h (120 min) plus tard.
    assert ds["target_h2"].iloc[10] == ds["consumption_kw"].iloc[10 + 2 * 60]
    # target_h1 (alias TARGET_COLUMN) inchangé par rapport au comportement historique.
    assert ds[TARGET_COLUMN].iloc[10] == ds["consumption_kw"].iloc[10 + 60]


def test_clean_multi_horizon_dataset_requires_all_48_targets():
    df = _multi_horizon_dataset_frame(300)
    df.loc[0, "target_h48"] = np.nan  # seule la ligne 0 perd sa cible T+48h

    cleaned = clean_multi_horizon_dataset(df)

    assert len(cleaned) == len(df) - 1
    assert not cleaned[MULTI_HORIZON_TARGET_COLUMNS].isna().any().any()


def test_split_train_val_test_multi_horizon_is_chronological_and_complete():
    df = _multi_horizon_dataset_frame(2000)
    train, validation, test = split_train_val_test_multi_horizon(df)

    assert train["measurement_date"].max() < validation["measurement_date"].min()
    assert validation["measurement_date"].max() < test["measurement_date"].min()
    for chunk in (train, validation, test):
        assert not chunk[FEATURE_COLUMNS + MULTI_HORIZON_TARGET_COLUMNS].isna().any().any()


def test_split_train_val_test_multi_horizon_raises_when_dataset_too_small():
    with pytest.raises(NotEnoughDataError):
        split_train_val_test_multi_horizon(_multi_horizon_dataset_frame(2))


# --- Features calendaires exclues du calcul de drift ------------------------


def test_drift_feature_columns_excludes_calendar_features():
    assert set(DRIFT_FEATURE_COLUMNS).isdisjoint(CALENDAR_FEATURE_COLUMNS)
    assert set(DRIFT_FEATURE_COLUMNS) <= set(FEATURE_COLUMNS)
