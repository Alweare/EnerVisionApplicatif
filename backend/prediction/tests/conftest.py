import os
import shutil
from pathlib import Path

import mlflow
import pytest

# prediction.repository.measurement_repository importe shared.database, qui lit
# POSTGRES_* au moment de l'import (os.environ[...]). On pose des valeurs
# factices pour que la collecte des tests fonctionne sans base réelle -- les
# tests ne touchent jamais la vraie connexion : pd.read_sql est monkeypatché.
os.environ.setdefault("POSTGRES_DB", "tests")
os.environ.setdefault("POSTGRES_APP_USER", "tests")
os.environ.setdefault("POSTGRES_APP_PWD", "tests")
os.environ.setdefault("DVC_ROOT", str(Path(__file__).resolve().parents[3]))

# Le scheduler de forecast est activé par défaut en production (config.py) :
# jamais pendant les tests, qu'un test déclenche ou non le lifespan FastAPI.
os.environ.setdefault("PREDICTION_SCHEDULER_ENABLED", "false")


@pytest.fixture(autouse=True)
def _no_stray_mlruns_dir():
    mlruns_dir = Path.cwd() / "mlruns"
    existed_before = mlruns_dir.exists()
    yield
    if not existed_before and mlruns_dir.exists():
        shutil.rmtree(mlruns_dir, ignore_errors=True)


@pytest.fixture
def mlflow_tracking_uri(tmp_path, monkeypatch):
    tracking_uri = f"sqlite:///{(tmp_path / 'mlflow.db').as_posix()}"
    artifact_location = (tmp_path / "artifacts").as_uri()

    monkeypatch.setenv("MLFLOW_TRACKING_URI", tracking_uri)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.create_experiment("consumption-prediction", artifact_location=artifact_location)
    mlflow.set_experiment("consumption-prediction")

    return tracking_uri
