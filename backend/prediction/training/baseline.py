from __future__ import annotations

import pandas as pd
from sklearn.metrics import mean_absolute_error

from prediction.dataset.dataset import HORIZONS_HOURS, ROWS_PER_HOUR, TARGET_COLUMN_PREFIX

BASELINE_FEATURE = "lag_1h"

# Au-delà de cet horizon, la persistance ("la conso ne bouge pas") cesse
# d'être une hypothèse raisonnable -- on bascule sur une règle saisonnière.
SHORT_HORIZON_MAX_HOURS = 24
# Période de la règle saisonnière au-delà de SHORT_HORIZON_MAX_HOURS : "même
# heure, la semaine précédente".
SEASONAL_PERIOD_HOURS = 168
BASELINE_COLUMN_PREFIX = "baseline_h"


def predict_baseline(X: pd.DataFrame) -> pd.Series:
    return X[BASELINE_FEATURE]


def baseline_mae(X: pd.DataFrame, y: pd.Series) -> float:
    return mean_absolute_error(y, predict_baseline(X))


def relative_improvement(reference_mae: float, candidate_mae: float) -> float:
    if reference_mae == 0:
        return 0.0 if candidate_mae == 0 else float("-inf")
    return (reference_mae - candidate_mae) / reference_mae


def _baseline_lag_hours(horizon_hours: int) -> int:
    """
    Nombre d'heures à remonter avant T pour obtenir la valeur baseline de
    l'horizon `horizon_hours`, toujours strictement dans le passé (jamais de
    fuite) :

    - h <= 24h : persistance -- "la conso dans h heures = la conso maintenant"
      (lag 0h, valeur en T). C'est la règle naïve la plus dure à battre à
      court terme (autocorrélation forte), donc la plus honnête comme
      référence.
    - h > 24h : saisonnalité hebdomadaire -- "même heure, la semaine
      précédente". Comme h <= 168h (SEASONAL_PERIOD_HOURS), T + h - 168h <= T :
      la valeur de référence est toujours déjà connue en T, quel que soit h
      (l'horizon maximal du forecast, MAX_HORIZON_HOURS, est aujourd'hui 48h,
      largement dans cette plage).
      Choisi plutôt qu'une règle "même heure hier" (qui ne serait valide que
      jusqu'à h=24h, redondante avec le régime de persistance) : une seule
      règle saisonnière suffit pour couvrir 25..168h simplement.
    """
    if horizon_hours <= SHORT_HORIZON_MAX_HOURS:
        return 0
    return SEASONAL_PERIOD_HOURS - horizon_hours


def attach_baseline_columns(
    df: pd.DataFrame, horizons_hours: list[int] = HORIZONS_HOURS
) -> pd.DataFrame:
    """
    Ajoute une colonne `baseline_h{h}` par horizon, calculée sur la série
    continue (avant tout split) pour que le décalage voit bien tout
    l'historique disponible -- calculer ceci après un split tronquerait les
    lags saisonniers pour les lignes proches du début d'un chunk.
    """
    grouped = df.groupby("site_id")["consumption_kw"]
    baselines = pd.concat(
        {
            f"{BASELINE_COLUMN_PREFIX}{horizon_hours}": grouped.shift(
                _baseline_lag_hours(horizon_hours) * ROWS_PER_HOUR
            )
            for horizon_hours in horizons_hours
        },
        axis=1,
    )
    return pd.concat([df, baselines], axis=1)


def multi_horizon_baseline_mae(
    df: pd.DataFrame, horizons_hours: list[int] = HORIZONS_HOURS
) -> dict[int, float]:
    """MAE de la baseline saisonnière par horizon, sur les lignes où cible ET
    baseline sont connues (colonnes ajoutées par `attach_baseline_columns`)."""
    maes: dict[int, float] = {}
    for horizon_hours in horizons_hours:
        target_column = f"{TARGET_COLUMN_PREFIX}{horizon_hours}"
        baseline_column = f"{BASELINE_COLUMN_PREFIX}{horizon_hours}"
        pair = df[[target_column, baseline_column]].dropna()
        maes[horizon_hours] = (
            mean_absolute_error(pair[target_column], pair[baseline_column])
            if len(pair)
            else float("nan")
        )
    return maes
