from __future__ import annotations

import pandas as pd

from prediction.dataset.dataset import FEATURE_COLUMNS
from prediction.features.time_features import add_time_features
from prediction.repository.measurement_repository import get_measurements


class InsufficientHistoryError(Exception):
    def __init__(self, site_id: str):
        self.site_id = site_id
        super().__init__(f"Historique insuffisant pour construire les features du site '{site_id}'")


def build_latest_features(site_id: str) -> tuple[pd.DataFrame, pd.Timestamp]:
    raw = get_measurements(site_id)
    if raw.empty:
        raise InsufficientHistoryError(site_id)

    enriched = add_time_features(raw)
    usable = enriched.dropna(subset=FEATURE_COLUMNS)
    if usable.empty:
        raise InsufficientHistoryError(site_id)

    latest = usable.tail(1)
    return latest[FEATURE_COLUMNS], latest.iloc[0]["measurement_date"]
