from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DEFAULT_N_BINS = 10
_PROPORTION_FLOOR = 1e-4


@dataclass(frozen=True)
class DriftResult:
    feature_scores: dict[str, float]
    drifted_features: list[str]
    threshold: float
    drift_detected: bool
    skipped_features: list[str] = field(default_factory=list)


def _bin_edges(values: np.ndarray, n_bins: int) -> np.ndarray:
    quantiles = np.linspace(0, 1, n_bins + 1)
    edges = np.unique(np.quantile(values, quantiles))
    if len(edges) < 2:
        edges = np.array([values.min(), values.max()])
        if edges[0] == edges[1]:
            edges = np.array([edges[0], edges[0] + 1.0])
    edges = edges.astype(float)
    edges[0] = -np.inf
    edges[-1] = np.inf
    return edges


def compute_reference_stats(
    df: pd.DataFrame, feature_columns: list[str], n_bins: int = DEFAULT_N_BINS
) -> dict:
    features = {}
    for feature in feature_columns:
        values = df[feature].dropna().to_numpy()
        if len(values) == 0:
            continue
        edges = _bin_edges(values, n_bins)
        counts, _ = np.histogram(values, bins=edges)
        proportions = counts / counts.sum()
        features[feature] = {
            "bin_edges": edges.tolist(),
            "reference_proportions": proportions.tolist(),
            "n_reference_rows": int(len(values)),
        }
    return {"n_bins": n_bins, "features": features}


def _population_stability_index(
    bin_edges: list[float], reference_proportions: list[float], current_values: np.ndarray
) -> float:
    counts, _ = np.histogram(current_values, bins=bin_edges)
    total = counts.sum()
    if total == 0:
        raise ValueError("Aucune valeur courante à comparer à la référence")

    current_proportions = counts / total
    reference = np.clip(np.asarray(reference_proportions), _PROPORTION_FLOOR, None)
    current = np.clip(current_proportions, _PROPORTION_FLOOR, None)

    return float(np.sum((current - reference) * np.log(current / reference)))


def detect_drift(
    reference_stats: dict,
    current_df: pd.DataFrame,
    threshold: float,
    feature_columns: list[str] | None = None,
) -> DriftResult:
    reference_features = reference_stats.get("features", {})
    feature_columns = feature_columns or list(reference_features.keys())

    scores: dict[str, float] = {}
    skipped: list[str] = []

    for feature in feature_columns:
        feature_reference = reference_features.get(feature)
        if feature_reference is None:
            skipped.append(feature)
            continue

        current_values = current_df[feature].dropna().to_numpy() if feature in current_df else np.array([])
        if len(current_values) == 0:
            skipped.append(feature)
            continue

        scores[feature] = _population_stability_index(
            feature_reference["bin_edges"],
            feature_reference["reference_proportions"],
            current_values,
        )

    drifted = [feature for feature, score in scores.items() if score >= threshold]

    return DriftResult(
        feature_scores=scores,
        drifted_features=drifted,
        threshold=threshold,
        drift_detected=bool(drifted),
        skipped_features=skipped,
    )
