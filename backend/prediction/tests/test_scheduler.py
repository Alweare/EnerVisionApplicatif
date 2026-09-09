"""
Tests de `scheduler/scheduler.py` (activation, configuration, concurrence) et
du lifespan FastAPI (démarrage/arrêt propre) -- cf. §Concurrence, §Tests.

Rapides et isolés : ni vrai APScheduler qui tourne, ni MLflow/Postgres/XGBoost
réels. `create_scheduler()` ne fait jamais `.start()` elle-même (vérifié
explicitement) -- démarrer un vrai scheduler n'est testé qu'au travers du
lifespan, avec un double qui n'exécute jamais le job pour de vrai.
"""

from datetime import timedelta

from apscheduler.triggers.interval import IntervalTrigger
from fastapi.testclient import TestClient

from prediction.api.app import app
from prediction.config import PredictionSettings
from prediction.scheduler.scheduler import FORECAST_JOB_ID, JOB_MISFIRE_GRACE_SECONDS, create_scheduler


class FakeService:
    def forecast(self, site_id: str, hours: int):
        raise AssertionError("le job ne doit jamais être exécuté par ces tests")


def _settings(**overrides) -> PredictionSettings:
    base = dict(
        mlflow_tracking_uri="",
        mlflow_experiment_name="consumption-prediction",
        mlflow_model_name="consumption-predictor",
        min_improvement_vs_baseline=0.05,
        min_improvement_vs_champion=0.01,
        drift_threshold=0.2,
        min_new_rows=1440,
    )
    base.update(overrides)
    return PredictionSettings(**base)


def test_create_scheduler_returns_none_when_disabled():
    settings = _settings(scheduler_enabled=False)

    scheduler = create_scheduler(settings=settings, prediction_service=FakeService())

    assert scheduler is None


def test_create_scheduler_never_starts_itself():
    settings = _settings(scheduler_enabled=True)

    scheduler = create_scheduler(settings=settings, prediction_service=FakeService())

    assert scheduler is not None
    assert scheduler.running is False


def test_create_scheduler_configures_the_interval_from_settings():
    settings = _settings(scheduler_enabled=True, forecast_interval_minutes=15, forecast_hours=48)

    scheduler = create_scheduler(settings=settings, prediction_service=FakeService())

    job = scheduler.get_job(FORECAST_JOB_ID)
    assert job is not None
    assert isinstance(job.trigger, IntervalTrigger)
    assert job.trigger.interval == timedelta(minutes=15)
    assert job.kwargs["hours"] == 48


def test_create_scheduler_prevents_overlapping_runs():
    settings = _settings(scheduler_enabled=True)

    scheduler = create_scheduler(settings=settings, prediction_service=FakeService())

    job = scheduler.get_job(FORECAST_JOB_ID)
    assert job.max_instances == 1
    assert job.coalesce is True
    assert job.misfire_grace_time == JOB_MISFIRE_GRACE_SECONDS


def test_create_scheduler_uses_the_injected_prediction_service():
    settings = _settings(scheduler_enabled=True)
    service = FakeService()

    scheduler = create_scheduler(settings=settings, prediction_service=service)

    job = scheduler.get_job(FORECAST_JOB_ID)
    assert job.kwargs["prediction_service"] is service


# --- Lifespan FastAPI : démarrage/arrêt propre -------------------------------


def test_lifespan_leaves_no_scheduler_when_disabled():
    # PREDICTION_SCHEDULER_ENABLED=false (tests/conftest.py) : c'est le cas
    # par défaut de toute la suite de tests, jamais de vrai scheduler.
    with TestClient(app) as client:
        assert app.state.scheduler is None
        response = client.get("/health")
        assert response.status_code == 200


def test_lifespan_starts_and_stops_the_scheduler_when_enabled(monkeypatch):
    calls = {"start": 0, "shutdown": 0}

    class FakeScheduler:
        def start(self):
            calls["start"] += 1

        def shutdown(self, wait=False):
            calls["shutdown"] += 1

    monkeypatch.setattr("prediction.api.app.create_scheduler", lambda: FakeScheduler())

    with TestClient(app) as client:
        assert isinstance(app.state.scheduler, FakeScheduler)
        assert calls["start"] == 1
        assert calls["shutdown"] == 0

    assert calls["shutdown"] == 1
