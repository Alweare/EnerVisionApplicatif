"""
Tests de `scheduler/forecast_job.py` (§Job de forecast, §Gestion des erreurs).

Aucune vraie base/MLflow/XGBoost : `PredictionService` est un double
(FakeService), `get_active_site_ids` est monkeypatché.
"""

import logging

import pytest

from prediction.observability import ml_metrics
from prediction.scheduler.forecast_job import ForecastJobResult, run_forecast_job


class FakeService:
    """Double de PredictionService.forecast -- ne construit ni features, ni
    modèle, ni ne touche MLflow/Postgres."""

    def __init__(self, failing_site_ids: set[str] | None = None):
        self.failing_site_ids = failing_site_ids or set()
        self.calls: list[tuple[str, int]] = []

    def forecast(self, site_id: str, hours: int):
        self.calls.append((site_id, hours))
        if site_id in self.failing_site_ids:
            raise RuntimeError(f"boom on {site_id}")


@pytest.fixture(autouse=True)
def _patch_sites(monkeypatch):
    monkeypatch.setattr(
        "prediction.scheduler.forecast_job.get_active_site_ids",
        lambda: ["SITE001", "SITE002", "SITE003"],
    )


def test_calls_forecast_for_every_active_site_with_configured_hours():
    service = FakeService()

    run_forecast_job(service, hours=48)

    assert service.calls == [("SITE001", 48), ("SITE002", 48), ("SITE003", 48)]


def test_error_on_one_site_does_not_prevent_the_others():
    service = FakeService(failing_site_ids={"SITE002"})

    result = run_forecast_job(service, hours=48)

    # Les 3 sites ont bien été tentés, pas seulement ceux avant l'échec.
    assert [site_id for site_id, _ in service.calls] == ["SITE001", "SITE002", "SITE003"]
    assert result.n_success == 2
    assert result.n_failed == 1
    assert result.failed_site_ids == ["SITE002"]


def test_result_counts_reflect_all_successes():
    service = FakeService()

    result = run_forecast_job(service, hours=48)

    assert result == ForecastJobResult(
        n_sites=3, n_success=3, n_failed=0, failed_site_ids=[], duration_seconds=result.duration_seconds
    )
    assert result.duration_seconds >= 0.0


def test_no_active_sites_returns_zero_counts(monkeypatch):
    monkeypatch.setattr("prediction.scheduler.forecast_job.get_active_site_ids", lambda: [])
    service = FakeService()

    result = run_forecast_job(service, hours=48)

    assert result.n_sites == 0
    assert result.n_success == 0
    assert result.n_failed == 0
    assert service.calls == []


def test_all_sites_failing_still_returns_a_result_not_an_exception():
    service = FakeService(failing_site_ids={"SITE001", "SITE002", "SITE003"})

    result = run_forecast_job(service, hours=48)

    assert result.n_success == 0
    assert result.n_failed == 3


def test_logs_start_and_finish_with_counts(caplog):
    service = FakeService(failing_site_ids={"SITE002"})

    with caplog.at_level(logging.INFO, logger="prediction.scheduler.forecast_job"):
        run_forecast_job(service, hours=48)

    events = [record.__dict__.get("event") for record in caplog.records]
    assert "scheduled_forecast_job_started" in events
    assert "scheduled_forecast_job_site_failed" in events
    assert "scheduled_forecast_job_finished" in events


def test_records_prometheus_metrics_for_the_run():
    before_runs = ml_metrics.SCHEDULED_FORECAST_JOB_RUNS_TOTAL._value.get()
    before_success = ml_metrics.SCHEDULED_FORECAST_JOB_SITES_TOTAL.labels(result="success")._value.get()
    before_failure = ml_metrics.SCHEDULED_FORECAST_JOB_SITES_TOTAL.labels(result="failure")._value.get()

    run_forecast_job(FakeService(failing_site_ids={"SITE002"}), hours=48)

    assert ml_metrics.SCHEDULED_FORECAST_JOB_RUNS_TOTAL._value.get() == before_runs + 1
    assert (
        ml_metrics.SCHEDULED_FORECAST_JOB_SITES_TOTAL.labels(result="success")._value.get()
        == before_success + 2
    )
    assert (
        ml_metrics.SCHEDULED_FORECAST_JOB_SITES_TOTAL.labels(result="failure")._value.get()
        == before_failure + 1
    )
