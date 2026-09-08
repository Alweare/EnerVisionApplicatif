import os

import mlflow
import mlflow.sklearn
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

MODEL_PARAMS = {"fit_intercept": True}


def train_model(X_train, y_train, dvc_hash: str | None = None):
    # Configuration MLflow à l'intérieur de la fonction, jamais au niveau
    # module : un appel au niveau module contacterait le serveur MLflow
    # dès l'import du fichier, empêchant tout test unitaire de rediriger
    # le tracking vers un stockage isolé avant que cet appel n'ait eu lieu.
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    mlflow.set_experiment("consumption-prediction")

    with mlflow.start_run() as run:
        model = LinearRegression(**MODEL_PARAMS)
        model.fit(X_train, y_train)

        mlflow.log_params(MODEL_PARAMS)
        mlflow.log_param("n_train_rows", len(X_train))
        if dvc_hash:
            mlflow.log_param("dvc_hash", dvc_hash)
        mlflow.sklearn.log_model(model, artifact_path="model", registered_model_name="consumption-predictor")

        return model, run.info.run_id


def evaluate_model(model, X_test, y_test, run_id):
    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))

    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)

    with mlflow.start_run(run_id=run_id):
        mlflow.log_metric("mae", mae)

    return mae