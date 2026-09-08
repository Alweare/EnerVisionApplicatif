import mlflow
import numpy as np
import pytest
from sklearn.linear_model import LinearRegression

from prediction.training.training_service import train_model, evaluate_model


@pytest.fixture
def clean_dataset():
    """
    Relation parfaitement linéaire :
    y = 2x

    La régression linéaire doit donc obtenir un MAE proche de 0.
    """
    X_train = np.array([
        [1],
        [2],
        [3],
        [4],
        [5],
    ])

    y_train = np.array([
        2,
        4,
        6,
        8,
        10,
    ])

    X_test = np.array([
        [6],
        [7],
        [8],
    ])

    y_test = np.array([
        12,
        14,
        16,
    ])

    return X_train, X_test, y_train, y_test


def test_train_model_returns_model_and_run_id(
    mlflow_tracking_uri,
    clean_dataset,
):
    X_train, _, y_train, _ = clean_dataset

    model, run_id, model_uri = train_model(
        X_train,
        y_train,
    )

    assert isinstance(model, LinearRegression)

    assert run_id is not None
    assert isinstance(run_id, str)
    assert len(run_id) > 0

    assert model_uri is not None
    assert isinstance(model_uri, str)
    assert model_uri.startswith("models:/")


def test_train_model_logged_model_is_actually_loadable(
    mlflow_tracking_uri,
    clean_dataset,
):
    """
    Critère d'acceptation : l'URI renvoyée par `train_model` doit pointer vers
    un artefact réellement récupérable, pas seulement vers un identifiant.
    """
    X_train, _, y_train, _ = clean_dataset

    model, _, model_uri = train_model(
        X_train,
        y_train,
    )

    reloaded = mlflow.sklearn.load_model(model_uri)

    assert reloaded.coef_ == pytest.approx(model.coef_)


def test_training_logs_expected_parameters(
    mlflow_tracking_uri,
    clean_dataset,
):
    X_train, _, y_train, _ = clean_dataset

    _, run_id, _ = train_model(
        X_train,
        y_train,
        dvc_hash="abc123",
    )

    run = mlflow.get_run(run_id)

    assert run.data.params["fit_intercept"] == "True"
    assert run.data.params["n_train_rows"] == str(len(X_train))
    assert run.data.params["dvc_hash"] == "abc123"


def test_evaluate_model_logs_mae_in_same_run(
    mlflow_tracking_uri,
    clean_dataset,
):
    X_train, X_test, y_train, y_test = clean_dataset

    model, run_id, _ = train_model(
        X_train,
        y_train,
    )

    mae = evaluate_model(
        model,
        X_test,
        y_test,
        run_id,
    )

    run = mlflow.get_run(run_id)

    assert "mae" in run.data.metrics
    assert run.data.metrics["mae"] == pytest.approx(mae)

    # Relation parfaitement linéaire y = 2x
    # donc erreur quasiment nulle.
    assert mae == pytest.approx(0.0, abs=1e-10)


def test_noisy_data_produces_higher_mae(
    mlflow_tracking_uri,
    clean_dataset,
):
    """
    Critère d'acceptation :
    une donnée bruitée doit produire un MAE supérieur
    à une relation propre.
    """
    X_train, X_test, y_train, y_test_clean = clean_dataset

    clean_model, clean_run_id, _ = train_model(
        X_train,
        y_train,
    )

    clean_mae = evaluate_model(
        clean_model,
        X_test,
        y_test_clean,
        clean_run_id,
    )

    noisy_y_test = np.array([
        20,
        5,
        30,
    ])

    noisy_model, noisy_run_id, _ = train_model(
        X_train,
        y_train,
    )

    noisy_mae = evaluate_model(
        noisy_model,
        X_test,
        noisy_y_test,
        noisy_run_id,
    )

    assert noisy_mae > clean_mae


def test_two_training_calls_create_different_runs(
    mlflow_tracking_uri,
    clean_dataset,
):
    """
    Critère d'acceptation :
    deux entraînements successifs doivent produire
    deux runs MLflow distincts.
    """
    X_train, _, y_train, _ = clean_dataset

    _, first_run_id, _ = train_model(
        X_train,
        y_train,
    )

    _, second_run_id, _ = train_model(
        X_train,
        y_train,
    )

    assert first_run_id != second_run_id


def test_evaluation_does_not_create_another_run(
    mlflow_tracking_uri,
    clean_dataset,
):
    """
    Vérifie que evaluate_model réutilise le run
    créé lors de l'entraînement.
    """
    X_train, X_test, y_train, y_test = clean_dataset

    _, experiment = mlflow.set_experiment(
        "consumption-prediction"
    ), mlflow.get_experiment_by_name(
        "consumption-prediction"
    )

    model, run_id, _ = train_model(
        X_train,
        y_train,
    )

    before_evaluation = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id]
    )

    run_count_before = len(before_evaluation)

    evaluate_model(
        model,
        X_test,
        y_test,
        run_id,
    )

    after_evaluation = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id]
    )

    run_count_after = len(after_evaluation)

    assert run_count_after == run_count_before