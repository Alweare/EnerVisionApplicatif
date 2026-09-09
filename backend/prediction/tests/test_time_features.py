"""
Tests des features temporelles (EN-37).

Tout est vérifié sur des DataFrames synthétiques -- aucune base réelle n'est
nécessaire pour ce ticket, la fonction testée est pure.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from prediction.features.time_features import (
    ROWS_PER_DAY,
    ROWS_PER_HOUR,
    ROWS_PER_WEEK,
    add_time_features,
)

START = datetime(2026, 1, 1)  # jeudi


def _site_frame(site_id, consumptions, null_reasons=None):
    """Construit une série d'une mesure par minute pour un site."""
    n = len(consumptions)
    if null_reasons is None:
        null_reasons = [None] * n
    return pd.DataFrame(
        {
            "site_id": site_id,
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "consumption_kw": [float(c) for c in consumptions],
            "data_quality": ["good"] * n,
            "null_reason": null_reasons,
        }
    )


# --- Critère : lags par site, jamais mélangés entre sites ------------------

def test_lags_are_computed_per_site_and_never_mixed():
    n = ROWS_PER_HOUR + 5
    site_a = _site_frame("SITE_A", [100 + i for i in range(n)])
    site_b = _site_frame("SITE_B", [500 + i for i in range(n)])
    # Ordre volontairement mélangé : add_time_features doit re-trier.
    df = pd.concat([site_b, site_a]).sample(frac=1, random_state=0)

    out = add_time_features(df)
    b = out[out.site_id == "SITE_B"].reset_index(drop=True)

    # Les 60 premières lignes de SITE_B n'ont pas d'antécédent 1 h -> NaN.
    assert b["lag_1h"].iloc[:ROWS_PER_HOUR].isna().all()
    # La 61e ligne pointe sur la 1re valeur de SITE_B (500), jamais SITE_A.
    assert b["lag_1h"].iloc[ROWS_PER_HOUR] == 500.0
    # Aucune valeur de SITE_A (100..) n'a fui dans les lags de SITE_B.
    assert (b["lag_1h"].dropna() >= 500.0).all()


# --- Critère : lag null quand l'historique est insuffisant ----------------

def test_lags_are_null_when_history_is_insufficient():
    n = ROWS_PER_HOUR + 40  # > 1 h, mais très en deçà de 24 h
    df = _site_frame("SITE_A", [100 + i for i in range(n)])

    out = add_time_features(df)

    # lag_1h : NaN sur les 60 premières lignes, renseigné ensuite.
    assert out["lag_1h"].iloc[:ROWS_PER_HOUR].isna().all()
    assert out["lag_1h"].iloc[ROWS_PER_HOUR:].notna().all()
    # lag_24h : jamais assez d'historique ici -> NaN partout, jamais 0.
    assert out["lag_24h"].isna().all()


# --- Critère (revue n°1) : shift() AVANT rolling() ------------------------

def test_rolling_mean_shifts_before_rolling_and_excludes_current_row():
    baseline = [10.0] * 100
    spike_index = 100
    consumptions = baseline + [10_000.0] + [10.0] * 20
    df = _site_frame("SITE_A", consumptions)

    out = add_time_features(df)

    # À T = 100, la fenêtre s'arrête à T-1 : moyenne des 100 valeurs à 10,
    # le pic de T lui-même est exclu.
    assert out["rolling_mean_24h"].iloc[spike_index] == pytest.approx(10.0)
    # Sans le shift(1), la moyenne inclurait le pic -> résultat très différent.
    without_shift = (sum(baseline) + 10_000.0) / (len(baseline) + 1)
    assert out["rolling_mean_24h"].iloc[spike_index] != pytest.approx(without_shift)


# --- Critère : aucune fuite de données (feature à T ⟂ conso à T) ----------

def test_no_data_leakage_from_current_row():
    n = 300
    rng = np.random.default_rng(0)
    df = _site_frame("SITE_A", list(100 + rng.normal(0, 5, n)))
    T = 150

    reference = add_time_features(df)

    poisoned = df.copy()
    poisoned.loc[T, "consumption_kw"] = 99_999.0
    poisoned_out = add_time_features(poisoned)

    # Aucune feature à T ne bouge quand on modifie consumption_kw à T.
    assert poisoned_out["rolling_mean_24h"].iloc[T] == reference["rolling_mean_24h"].iloc[T]
    assert poisoned_out["lag_1h"].iloc[T] == reference["lag_1h"].iloc[T]

    # En revanche la valeur modifiée se propage bien aux lignes SUIVANTES :
    # preuve que ce test détecterait une fuite si elle existait.
    assert (
        poisoned_out["rolling_mean_24h"].iloc[T + 1]
        != reference["rolling_mean_24h"].iloc[T + 1]
    )


# --- Prétraitement : neutralisation des consommations forward-fillées -----

def test_tainted_consumption_is_neutralized_but_row_is_kept():
    n = ROWS_PER_HOUR + 20
    consumptions = [100.0] * n
    null_reasons = [None] * n
    # Ligne 5 : perte réseau -> consumption_kw recopiée. Valeur "poison".
    consumptions[5] = 99_999.0
    null_reasons[5] = ["network_loss"]
    # Ligne 6 : panne capteur température seule -> consumption_kw réelle.
    null_reasons[6] = ["temperature_sensor_failure"]

    df = _site_frame("SITE_A", consumptions, null_reasons)
    out = add_time_features(df)

    # La ligne dégradée est conservée (sinon les lags se décalent) et les
    # colonnes qualité restent disponibles pour l'étape d'entraînement.
    assert len(out) == n
    assert {"data_quality", "null_reason"} <= set(out.columns)

    # La valeur poison de la ligne 5 ne nourrit aucun lag en aval...
    assert np.isnan(out["lag_1h"].iloc[5 + ROWS_PER_HOUR])
    # ... ni la moyenne glissante (qui reste à 100, pas tirée vers 99 999).
    assert out["rolling_mean_24h"].iloc[10] == pytest.approx(100.0)

    # La ligne 6 (température uniquement) garde sa consommation réelle.
    assert out["lag_1h"].iloc[6 + ROWS_PER_HOUR] == 100.0


# --- Forecast multi-horizon : lag_168h / rolling_mean_168h -----------------

def test_lag_168h_is_null_when_history_is_insufficient():
    n = ROWS_PER_WEEK - 10  # juste avant 7 jours d'historique
    df = _site_frame("SITE_A", [100 + i for i in range(n)])

    out = add_time_features(df)

    assert out["lag_168h"].isna().all()


def test_lag_168h_matches_value_one_week_earlier_per_site():
    n = ROWS_PER_WEEK + 5
    site_a = _site_frame("SITE_A", [100 + i for i in range(n)])
    site_b = _site_frame("SITE_B", [500 + i for i in range(n)])
    df = pd.concat([site_b, site_a]).sample(frac=1, random_state=0)

    out = add_time_features(df)
    a = out[out.site_id == "SITE_A"].reset_index(drop=True)

    assert a["lag_168h"].iloc[ROWS_PER_WEEK] == 100.0
    # Aucune fuite entre sites.
    assert (a["lag_168h"].dropna() < 500.0).all()


def test_rolling_mean_168h_shifts_before_rolling_and_excludes_current_row():
    baseline = [10.0] * 200
    spike_index = 200
    consumptions = baseline + [10_000.0] + [10.0] * 20
    df = _site_frame("SITE_A", consumptions)

    out = add_time_features(df)

    assert out["rolling_mean_168h"].iloc[spike_index] == pytest.approx(10.0)


# --- Forecast multi-horizon : features calendaires --------------------------

def test_calendar_features_are_deterministic_from_measurement_date():
    # START = 2026-01-01 00:00, un jeudi.
    n = 4 * ROWS_PER_DAY
    df = _site_frame("SITE_A", [1.0] * n)

    out = add_time_features(df)

    first_row = out.iloc[0]
    assert first_row["hour_of_day"] == 0
    assert first_row["day_of_week"] == 3  # jeudi (Monday=0)
    assert first_row["is_weekend"] == 0

    # 3 jours plus tard (dimanche) à 14h -> ligne à l'index 3*1440 + 14*60.
    sunday_14h_index = 3 * ROWS_PER_DAY + 14 * ROWS_PER_HOUR
    sunday_row = out.iloc[sunday_14h_index]
    assert sunday_row["hour_of_day"] == 14
    assert sunday_row["day_of_week"] == 6  # dimanche
    assert sunday_row["is_weekend"] == 1


def test_calendar_features_never_depend_on_consumption_value():
    n = 500
    rng = np.random.default_rng(0)
    df = _site_frame("SITE_A", list(100 + rng.normal(0, 5, n)))

    reference = add_time_features(df)

    poisoned = df.copy()
    poisoned.loc[100, "consumption_kw"] = 99_999.0
    poisoned_out = add_time_features(poisoned)

    for column in ("hour_of_day", "day_of_week", "is_weekend"):
        pd.testing.assert_series_equal(
            reference[column], poisoned_out[column], check_names=False
        )
