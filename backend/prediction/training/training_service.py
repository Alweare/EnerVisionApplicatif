import mlflow
import mlflow.sklearn
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

MODEL_PARAMS = {"fit_intercept": True}


def train_model(X_train, y_train, dvc_hash: str | None = None):
    with mlflow.start_run() as run:
        model = LinearRegression(**MODEL_PARAMS)
        model.fit(X_train, y_train)

        mlflow.log_params(MODEL_PARAMS)
        mlflow.log_param("n_train_rows", len(X_train))

        if dvc_hash:
            mlflow.log_param("dvc_hash", dvc_hash)

        model_info = mlflow.sklearn.log_model(
            model,
            name="model",
        )

        return model, run.info.run_id, model_info.model_uri


def evaluate_model(model, X_test, y_test, run_id):
    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)

    with mlflow.start_run(run_id=run_id):
        mlflow.log_metric("mae", mae)

    return mae