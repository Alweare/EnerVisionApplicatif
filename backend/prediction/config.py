import os
from dataclasses import dataclass

DEFAULT_MLFLOW_TRACKING_URI = "http://mlflow:5000"
DEFAULT_MLFLOW_EXPERIMENT_NAME = "consumption-prediction"
DEFAULT_MLFLOW_MODEL_NAME = "consumption-predictor"
DEFAULT_MIN_IMPROVEMENT_VS_BASELINE = 0.05
DEFAULT_MIN_IMPROVEMENT_VS_CHAMPION = 0.01
DEFAULT_DRIFT_THRESHOLD = 0.2
DEFAULT_MIN_NEW_ROWS = 1440

CHAMPION_ALIAS = "champion"
CHALLENGER_ALIAS = "challenger"


@dataclass(frozen=True)
class PredictionSettings:
    mlflow_tracking_uri: str
    mlflow_experiment_name: str
    mlflow_model_name: str
    min_improvement_vs_baseline: float
    min_improvement_vs_champion: float
    drift_threshold: float
    min_new_rows: int


def _float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    return default if value is None or value == "" else float(value)


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    return default if value is None or value == "" else int(value)


def get_settings() -> PredictionSettings:
    return PredictionSettings(
        mlflow_tracking_uri=os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_MLFLOW_TRACKING_URI),
        mlflow_experiment_name=os.environ.get(
            "MLFLOW_EXPERIMENT_NAME", DEFAULT_MLFLOW_EXPERIMENT_NAME
        ),
        mlflow_model_name=os.environ.get("MLFLOW_MODEL_NAME", DEFAULT_MLFLOW_MODEL_NAME),
        min_improvement_vs_baseline=_float_env(
            "MIN_IMPROVEMENT_VS_BASELINE", DEFAULT_MIN_IMPROVEMENT_VS_BASELINE
        ),
        min_improvement_vs_champion=_float_env(
            "MIN_IMPROVEMENT_VS_CHAMPION", DEFAULT_MIN_IMPROVEMENT_VS_CHAMPION
        ),
        drift_threshold=_float_env("DRIFT_THRESHOLD", DEFAULT_DRIFT_THRESHOLD),
        min_new_rows=_int_env("MIN_NEW_ROWS", DEFAULT_MIN_NEW_ROWS),
    )
