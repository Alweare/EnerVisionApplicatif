import numpy as np
import pandas as pd
import pytest

from prediction.drift.drift_service import compute_reference_stats, detect_drift

FEATURES = ["lag_1h", "lag_24h", "rolling_mean_24h"]


def _stable_frame(n=1000, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "lag_1h": rng.normal(loc=50, scale=5, size=n),
            "lag_24h": rng.normal(loc=50, scale=5, size=n),
            "rolling_mean_24h": rng.normal(loc=50, scale=5, size=n),
        }
    )


def _shifted_frame(n=1000, seed=1, shift=100):
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "lag_1h": rng.normal(loc=50 + shift, scale=5, size=n),
            "lag_24h": rng.normal(loc=50, scale=5, size=n),
            "rolling_mean_24h": rng.normal(loc=50, scale=5, size=n),
        }
    )


def test_compute_reference_stats_has_entry_per_feature():
    stats = compute_reference_stats(_stable_frame(), FEATURES)
    assert set(stats["features"].keys()) == set(FEATURES)
    for feature in FEATURES:
        assert len(stats["features"][feature]["bin_edges"]) >= 2
        assert stats["features"][feature]["n_reference_rows"] == 1000


def test_compute_reference_stats_skips_feature_without_data():
    df = pd.DataFrame({"lag_1h": [1.0, 2.0], "lag_24h": [np.nan, np.nan]})
    stats = compute_reference_stats(df, ["lag_1h", "lag_24h"])
    assert "lag_1h" in stats["features"]
    assert "lag_24h" not in stats["features"]


def test_detect_drift_reports_no_drift_on_identical_distribution():
    reference = _stable_frame(seed=0)
    stats = compute_reference_stats(reference, FEATURES)

    same_distribution = _stable_frame(seed=42)
    result = detect_drift(stats, same_distribution, threshold=0.2)

    assert result.drift_detected is False
    assert result.drifted_features == []
    for score in result.feature_scores.values():
        assert score < 0.2


def test_detect_drift_reports_drift_on_shifted_feature():
    reference = _stable_frame(seed=0)
    stats = compute_reference_stats(reference, FEATURES)

    shifted = _shifted_frame(seed=1)
    result = detect_drift(stats, shifted, threshold=0.2)

    assert result.drift_detected is True
    assert "lag_1h" in result.drifted_features
    assert result.feature_scores["lag_1h"] > result.threshold


def test_detect_drift_only_flags_the_drifted_feature():
    reference = _stable_frame(seed=0)
    stats = compute_reference_stats(reference, FEATURES)

    shifted = _shifted_frame(seed=1)
    result = detect_drift(stats, shifted, threshold=0.2)

    assert "lag_24h" not in result.drifted_features
    assert "rolling_mean_24h" not in result.drifted_features


def test_detect_drift_skips_features_missing_from_reference_or_current():
    reference = _stable_frame(seed=0)
    stats = compute_reference_stats(reference[["lag_1h"]], ["lag_1h"])

    result = detect_drift(stats, _stable_frame(seed=1), threshold=0.2, feature_columns=FEATURES)

    assert result.skipped_features == ["lag_24h", "rolling_mean_24h"]
    assert set(result.feature_scores.keys()) == {"lag_1h"}


def test_detect_drift_skips_feature_with_no_current_values():
    reference = _stable_frame(seed=0)
    stats = compute_reference_stats(reference, FEATURES)

    current = _stable_frame(seed=1)
    current["lag_1h"] = np.nan

    result = detect_drift(stats, current, threshold=0.2)

    assert "lag_1h" in result.skipped_features
    assert "lag_1h" not in result.feature_scores


def test_detect_drift_threshold_is_configurable():
    reference = _stable_frame(seed=0)
    stats = compute_reference_stats(reference, FEATURES)
    same_distribution = _stable_frame(seed=42)

    lenient = detect_drift(stats, same_distribution, threshold=999.0)
    strict = detect_drift(stats, same_distribution, threshold=0.0)

    assert lenient.drift_detected is False
    assert strict.drift_detected is True
