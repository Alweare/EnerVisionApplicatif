from datetime import datetime, timedelta

import pandas as pd
import pytest
from mlflow.tracking import MlflowClient

from prediction.config import PredictionSettings
from prediction.dataset.dataset import DRIFT_FEATURE_COLUMNS, MAX_HORIZON_HOURS
from prediction.registry.model_registry import get_model_version_by_alias
from prediction.training.pipeline import _decide_promotion, run_training_pipeline

START = datetime(2026, 1, 1)
MODEL_NAME = "consumption-predictor"

# Le modèle multi-horizon exige lag_168h/target_h168 (10080 lignes avant ET
# après une ligne pour qu'elle soit exploitable) : il faut donc nettement plus
# de 7+7 jours d'historique synthétique qu'avec l'ancien modèle T+1h seul.
N_ROWS = 25_000  # ~17.4 jours à 1 mesure/minute


def _linear_raw_frame(n: int = N_ROWS) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "site_id": "SITE_A",
            "measurement_date": [START + timedelta(minutes=i) for i in range(n)],
            "consumption_kw": [float(i) for i in range(n)],
            "data_quality": "good",
            "null_reason": None,
        }
    )


@pytest.fixture(autouse=True)
def _patch_measurements(monkeypatch):
    raw = _linear_raw_frame()
    monkeypatch.setattr("prediction.dataset.dataset.get_measurements", lambda: raw.copy())


def _settings(**overrides) -> PredictionSettings:
    base = dict(
        mlflow_tracking_uri="",
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name=MODEL_NAME,
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )
    base.update(overrides)
    return PredictionSettings(**base)


def test_first_candidate_becomes_champion_when_it_beats_baseline(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)

    result = run_training_pipeline(settings=settings)

    assert result.promoted is True
    assert result.champion_mae is None
    assert result.champion_mae_by_key_horizon is None
    assert result.champion_unavailable is False
    assert result.mae < result.baseline_mae

    # Évaluation par horizon (§7 du besoin) : la MAE ne doit jamais être
    # masquée par une seule valeur globale. Sur une série parfaitement
    # linéaire, la régression est quasi parfaite à chaque horizon (très en
    # dessous de la baseline), qui elle se dégrade nettement avec l'horizon.
    assert result.mae_h1 < 1.0
    assert result.mae_h24 < 1.0
    assert result.mae_h168 < 1.0
    assert result.baseline_mae_h1 < result.baseline_mae_h24 < result.baseline_mae_h168
    assert len(result.mae_by_horizon) == MAX_HORIZON_HOURS
    assert len(result.baseline_mae_by_horizon) == MAX_HORIZON_HOURS
    assert result.mae_mean < 1.0

    client = MlflowClient()
    champion = client.get_model_version_by_alias(MODEL_NAME, "champion")
    assert str(champion.version) == result.model_version


def test_candidate_rejected_when_it_does_not_beat_baseline(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_baseline=1.5)

    result = run_training_pipeline(settings=settings)

    assert result.promoted is False
    assert "baseline" in result.reason

    client = MlflowClient()
    assert get_model_version_by_alias(client, MODEL_NAME, "champion") is None
    rejected_version = client.get_model_version(MODEL_NAME, result.model_version)
    assert rejected_version.tags.get("rejected") == "true"


def test_better_challenger_replaces_champion(mlflow_tracking_uri):
    first_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=first_settings)
    assert first.promoted is True

    lenient_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_champion=-1.0)
    second = run_training_pipeline(settings=lenient_settings)

    assert second.promoted is True
    assert second.champion_mae is not None

    client = MlflowClient()
    champion = client.get_model_version_by_alias(MODEL_NAME, "champion")
    assert str(champion.version) == second.model_version
    assert str(champion.version) != first.model_version


def test_worse_challenger_is_rejected_and_champion_is_unchanged(mlflow_tracking_uri):
    first_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=first_settings)
    assert first.promoted is True

    strict_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_champion=0.9)
    second = run_training_pipeline(settings=strict_settings)

    assert second.promoted is False
    assert "champion" in second.reason

    client = MlflowClient()
    champion = client.get_model_version_by_alias(MODEL_NAME, "champion")
    assert str(champion.version) == first.model_version

    rejected = client.get_model_version(MODEL_NAME, second.model_version)
    assert rejected.tags.get("rejected") == "true"


def test_history_of_all_versions_is_preserved(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=settings)

    lenient_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_champion=-1.0)
    second = run_training_pipeline(settings=lenient_settings)

    client = MlflowClient()
    all_versions = client.search_model_versions(f"name='{MODEL_NAME}'")
    versions = {str(v.version) for v in all_versions}

    assert first.model_version in versions
    assert second.model_version in versions
    assert client.get_model_version(MODEL_NAME, first.model_version) is not None


def test_drift_is_none_on_first_run_and_computed_on_second_run(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=settings)
    assert first.drift_result is None

    second = run_training_pipeline(settings=settings)
    assert second.drift_result is not None
    assert set(second.drift_result.feature_scores.keys()) <= set(DRIFT_FEATURE_COLUMNS)
    # Les features calendaires (hour_of_day, day_of_week, is_weekend) ne
    # participent jamais au calcul de drift (§13 du besoin).
    assert "hour_of_day" not in second.drift_result.feature_scores
    assert "day_of_week" not in second.drift_result.feature_scores
    assert "is_weekend" not in second.drift_result.feature_scores


def test_broken_champion_does_not_block_training_and_is_recovered(mlflow_tracking_uri, tmp_path):
    import shutil

    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=settings)
    assert first.promoted is True

    shutil.rmtree(tmp_path / "artifacts", ignore_errors=True)

    second = run_training_pipeline(settings=settings)

    assert second.champion_unavailable is True
    assert second.promoted is True
    assert "could not be loaded" in second.reason

    client = MlflowClient()
    champion = client.get_model_version_by_alias(MODEL_NAME, "champion")
    assert str(champion.version) == second.model_version
    assert champion.tags.get("recovered_from_broken_champion") == "true"


def test_broken_champion_candidate_still_rejected_if_it_does_not_beat_baseline(mlflow_tracking_uri, tmp_path):
    import shutil

    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    first = run_training_pipeline(settings=settings)
    assert first.promoted is True

    shutil.rmtree(tmp_path / "artifacts", ignore_errors=True)

    strict_settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri, min_improvement_vs_baseline=1.5)
    second = run_training_pipeline(settings=strict_settings)

    assert second.champion_unavailable is True
    assert second.promoted is False
    assert "baseline" in second.reason


def test_logged_run_has_expected_params_and_metrics(mlflow_tracking_uri):
    settings = _settings(mlflow_tracking_uri=mlflow_tracking_uri)
    result = run_training_pipeline(settings=settings, trigger_source="cli_train_if_needed", retrain_reasons=["no_existing_champion"])

    client = MlflowClient()
    run = client.get_run(result.run_id)

    assert "n_validation_rows" in run.data.params
    assert "n_test_rows" in run.data.params
    assert "dataset_max_date" in run.data.params
    assert run.data.params["horizons_hours"] == f"1-{MAX_HORIZON_HOURS}"
    assert run.data.metrics["mae"] == pytest.approx(result.mae)
    assert run.data.metrics["baseline_mae"] == pytest.approx(result.baseline_mae)
    assert run.data.tags["trigger_source"] == "cli_train_if_needed"
    assert run.data.tags["retrain_reasons"] == "no_existing_champion"

    # Horizons clés (§7/§10 du besoin) : lisibles comme métriques MLflow
    # scalaires, jamais 168 métriques séparées.
    assert run.data.metrics["mae_h1"] == pytest.approx(result.mae_h1)
    assert run.data.metrics["mae_h24"] == pytest.approx(result.mae_h24)
    assert run.data.metrics["mae_h168"] == pytest.approx(result.mae_h168)
    assert run.data.metrics["baseline_mae_h1"] == pytest.approx(result.baseline_mae_h1)
    assert run.data.metrics["baseline_mae_h24"] == pytest.approx(result.baseline_mae_h24)
    assert run.data.metrics["baseline_mae_h168"] == pytest.approx(result.baseline_mae_h168)
    assert run.data.metrics["mae_mean"] == pytest.approx(result.mae_mean)

    # Détail des 168 horizons : artefact JSON, pas 168 métriques MLflow.
    artifacts = [artifact.path for artifact in client.list_artifacts(result.run_id)]
    assert "mae_by_horizon.json" in artifacts


# --- Règle de promotion multi-horizon (§9 du besoin), en isolation ---------


def test_decide_promotion_rejects_candidate_worse_than_baseline_at_long_horizon_even_if_great_at_h1():
    """
    Un candidat excellent à T+1h/T+24h mais moins bon que la baseline à T+168h
    ne doit jamais être promu -- même s'il n'y a pas encore de champion.
    """
    settings = _settings(mlflow_tracking_uri="")

    promoted, reason = _decide_promotion(
        settings=settings,
        has_champion=False,
        champion_unavailable=False,
        mae_by_key_horizon={1: 0.1, 24: 0.2, 168: 150.0},
        baseline_mae_by_key_horizon={1: 1.0, 24: 1.0, 168: 100.0},
        champion_mae_by_key_horizon=None,
    )

    assert promoted is False
    assert "168" in reason


def test_decide_promotion_promotes_when_candidate_beats_baseline_at_every_key_horizon():
    settings = _settings(mlflow_tracking_uri="")

    promoted, reason = _decide_promotion(
        settings=settings,
        has_champion=False,
        champion_unavailable=False,
        mae_by_key_horizon={1: 0.1, 24: 0.1, 168: 0.1},
        baseline_mae_by_key_horizon={1: 1.0, 24: 1.0, 168: 1.0},
        champion_mae_by_key_horizon=None,
    )

    assert promoted is True


def test_decide_promotion_rejects_when_candidate_does_not_beat_champion_at_h168_only():
    settings = _settings(mlflow_tracking_uri="")

    promoted, reason = _decide_promotion(
        settings=settings,
        has_champion=True,
        champion_unavailable=False,
        mae_by_key_horizon={1: 0.05, 24: 0.05, 168: 50.0},
        baseline_mae_by_key_horizon={1: 1.0, 24: 1.0, 168: 100.0},
        champion_mae_by_key_horizon={1: 1.0, 24: 1.0, 168: 50.1},
    )

    assert promoted is False
    assert "champion" in reason
    assert "168" in reason
