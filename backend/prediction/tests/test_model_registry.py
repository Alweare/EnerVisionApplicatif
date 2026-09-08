import mlflow
import numpy as np
import pytest
from mlflow.tracking import MlflowClient
from sklearn.linear_model import LinearRegression

from prediction.config import CHALLENGER_ALIAS, CHAMPION_ALIAS
from prediction.registry import model_registry as registry

MODEL_NAME = "consumption-predictor"


def _log_model_run(X, y) -> str:
    with mlflow.start_run() as run:
        model = LinearRegression()
        model.fit(X, y)
        mlflow.sklearn.log_model(model, artifact_path="model")
        return run.info.run_id


@pytest.fixture
def X_y():
    X = np.array([[1], [2], [3], [4], [5]])
    y = np.array([2, 4, 6, 8, 10])
    return X, y


def test_get_champion_version_returns_none_when_no_champion(mlflow_tracking_uri):
    client = MlflowClient()
    assert registry.get_champion_version(client, MODEL_NAME) is None


def test_register_challenger_sets_alias_and_candidate_tag(mlflow_tracking_uri, X_y):
    client = MlflowClient()
    run_id = _log_model_run(*X_y)

    version = registry.register_challenger(client, MODEL_NAME, run_id)

    challenger = registry.get_model_version_by_alias(client, MODEL_NAME, CHALLENGER_ALIAS)
    assert challenger.version == version.version
    assert version.tags.get("candidate") == "true"


def test_promote_to_champion_sets_alias_and_tags(mlflow_tracking_uri, X_y):
    client = MlflowClient()
    run_id = _log_model_run(*X_y)
    version = registry.register_challenger(client, MODEL_NAME, run_id)

    registry.promote_to_champion(client, MODEL_NAME, version.version, reason="beats baseline and champion")

    champion = registry.get_champion_version(client, MODEL_NAME)
    assert champion.version == version.version
    assert champion.tags.get("promoted") == "true"
    assert champion.tags.get("rejected") == "false"
    assert champion.tags.get("reason") == "beats baseline and champion"


def test_promote_to_champion_clears_challenger_alias(mlflow_tracking_uri, X_y):
    client = MlflowClient()
    run_id = _log_model_run(*X_y)
    version = registry.register_challenger(client, MODEL_NAME, run_id)

    registry.promote_to_champion(client, MODEL_NAME, version.version, reason="ok")

    assert registry.get_model_version_by_alias(client, MODEL_NAME, CHALLENGER_ALIAS) is None


def test_reject_challenger_does_not_delete_model_version(mlflow_tracking_uri, X_y):
    client = MlflowClient()
    run_id = _log_model_run(*X_y)
    version = registry.register_challenger(client, MODEL_NAME, run_id)

    registry.reject_challenger(client, MODEL_NAME, version.version, reason="worse than baseline")

    still_there = client.get_model_version(MODEL_NAME, version.version)
    assert still_there.tags.get("rejected") == "true"
    assert still_there.tags.get("promoted") == "false"
    assert registry.get_champion_version(client, MODEL_NAME) is None


def test_load_champion_model_returns_usable_model(mlflow_tracking_uri, X_y):
    client = MlflowClient()
    run_id = _log_model_run(*X_y)
    version = registry.register_challenger(client, MODEL_NAME, run_id)
    registry.promote_to_champion(client, MODEL_NAME, version.version, reason="first champion")

    model = registry.load_champion_model(MODEL_NAME)
    prediction = model.predict(np.array([[6]]))

    assert prediction[0] == pytest.approx(12.0, abs=1e-6)


def test_history_is_preserved_across_promotions(mlflow_tracking_uri, X_y):
    client = MlflowClient()

    first_run = _log_model_run(*X_y)
    first_version = registry.register_challenger(client, MODEL_NAME, first_run)
    registry.promote_to_champion(client, MODEL_NAME, first_version.version, reason="first champion")

    second_run = _log_model_run(*X_y)
    second_version = registry.register_challenger(client, MODEL_NAME, second_run)
    registry.promote_to_champion(client, MODEL_NAME, second_version.version, reason="better challenger")

    champion = registry.get_champion_version(client, MODEL_NAME)
    assert champion.version == second_version.version

    previous = client.get_model_version(MODEL_NAME, first_version.version)
    assert previous is not None
    assert previous.tags.get("promoted") == "true"


def test_drift_reference_roundtrip(mlflow_tracking_uri, X_y):
    client = MlflowClient()
    reference = {"n_bins": 10, "features": {"lag_1h": {"bin_edges": [1, 2], "reference_proportions": [1.0]}}}

    with mlflow.start_run() as run:
        model = LinearRegression()
        model.fit(*X_y)
        mlflow.sklearn.log_model(model, artifact_path="model")
        registry.save_drift_reference(reference)
        run_id = run.info.run_id

    version = registry.register_challenger(client, MODEL_NAME, run_id)

    loaded = registry.load_drift_reference(client, version)
    assert loaded == reference


def test_load_drift_reference_returns_none_when_missing(mlflow_tracking_uri, X_y):
    client = MlflowClient()
    run_id = _log_model_run(*X_y)
    version = registry.register_challenger(client, MODEL_NAME, run_id)

    assert registry.load_drift_reference(client, version) is None


def test_get_run_metric_and_param(mlflow_tracking_uri):
    with mlflow.start_run() as run:
        mlflow.log_param("fit_intercept", "True")
        mlflow.log_metric("mae", 1.23)
        run_id = run.info.run_id

    client = MlflowClient()
    assert registry.get_run_metric(client, run_id, "mae") == pytest.approx(1.23)
    assert registry.get_run_param(client, run_id, "fit_intercept") == "True"
    assert registry.get_run_metric(client, run_id, "missing") is None


def test_count_runs_with_tag(mlflow_tracking_uri):
    experiment = mlflow.get_experiment_by_name("consumption-prediction")

    with mlflow.start_run(tags={"trigger_source": "cli_train_if_needed"}):
        pass
    with mlflow.start_run(tags={"trigger_source": "cli_train"}):
        pass

    client = MlflowClient()
    count = registry.count_runs_with_tag(
        client, experiment.experiment_id, "trigger_source", "cli_train_if_needed"
    )
    assert count == 1


def test_count_versions_with_tag(mlflow_tracking_uri, X_y):
    client = MlflowClient()
    run_id = _log_model_run(*X_y)
    version = registry.register_challenger(client, MODEL_NAME, run_id)
    registry.reject_challenger(client, MODEL_NAME, version.version, reason="worse than baseline")

    assert registry.count_versions_with_tag(client, MODEL_NAME, "rejected", "true") == 1
    assert registry.count_versions_with_tag(client, MODEL_NAME, "promoted", "true") == 0
