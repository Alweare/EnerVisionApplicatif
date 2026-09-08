from __future__ import annotations

import pandas as pd
from sklearn.metrics import mean_absolute_error

BASELINE_FEATURE = "lag_1h"


def predict_baseline(X: pd.DataFrame) -> pd.Series:
    return X[BASELINE_FEATURE]


def baseline_mae(X: pd.DataFrame, y: pd.Series) -> float:
    return mean_absolute_error(y, predict_baseline(X))


def relative_improvement(reference_mae: float, candidate_mae: float) -> float:
    if reference_mae == 0:
        return 0.0 if candidate_mae == 0 else float("-inf")
    return (reference_mae - candidate_mae) / reference_mae
