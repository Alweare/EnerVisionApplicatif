import mlflow
import mlflow.sklearn

from sklearn.metrics import mean_absolute_error
from sklearn.multioutput import MultiOutputRegressor
from xgboost import XGBRegressor

MODEL_PARAMS = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "objective": "reg:squarederror",
    "random_state": 42,
    "n_jobs": -1,
}


def train_model(X_train, y_train, dvc_hash: str | None = None):
    with mlflow.start_run() as run:
        base_model = XGBRegressor(**MODEL_PARAMS)

        model = MultiOutputRegressor(base_model)

        model.fit(X_train, y_train)

        mlflow.log_params(MODEL_PARAMS)
        mlflow.log_param("model_type", "XGBRegressor")
        mlflow.log_param("multi_output_strategy", "MultiOutputRegressor")
        mlflow.log_param("n_train_rows", len(X_train))

        if dvc_hash:
            mlflow.log_param("dvc_hash", dvc_hash)

        model_info = mlflow.sklearn.log_model(
            model,
            name="model",
            skops_trusted_types=[
                "xgboost.core.Booster",
                "xgboost.sklearn.XGBRegressor",
            ],
        )

        return model, run.info.run_id, model_info.model_uri


def evaluate_model(model, X_test, y_test, run_id):
    predictions = model.predict(X_test)
    mae = mean_absolute_error(y_test, predictions)

    with mlflow.start_run(run_id=run_id):
        mlflow.log_metric("mae", mae)

    return mae