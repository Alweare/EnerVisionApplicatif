from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from core.api.schemas import (
    HistoryPoint,
    PredictionRead,
    SitePredictionRead,
)
from core.api.service.prediction_service import (
    PredictionNotAvailableError,
    PredictionService,
    SiteNotFoundError,
)


@pytest.fixture
def prediction_service():
    service = PredictionService.__new__(PredictionService)
    service.repository = Mock()
    service.site_repository = Mock()
    service.measurement_repository = Mock()
    return service


def _prediction(
    hour: int = 18,
    consumption_kw: float = 145.0,
    model_version: str | None = "v0.1.0-seed",
) -> PredictionRead:
    return PredictionRead(
        prediction_id=uuid4(),
        site_id="SITE001",
        predicted_for=datetime(2026, 9, 8, hour, 0, 0),
        predicted_consumption_kw=consumption_kw,
        model_version=model_version,
        created_at=datetime(2026, 9, 8, 11, 0, 0),
    )


def _history_point(hour: int, consumption_kw: float = 100.0) -> HistoryPoint:
    return HistoryPoint(
        measured_at=datetime(2026, 9, 8, hour, 0, 0),
        consumption_kw=consumption_kw,
    )


# --- get_prediction ------------------------------------------------------

def test_get_prediction_raises_when_site_unknown(prediction_service):
    prediction_service.site_repository.exists.return_value = False

    with pytest.raises(SiteNotFoundError) as error:
        prediction_service.get_prediction("SITE999")

    assert error.value.site_id == "SITE999"
    prediction_service.repository.list_projection_by_site.assert_not_called()


def test_get_prediction_raises_when_projection_empty(prediction_service):
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.list_projection_by_site.return_value = []

    with pytest.raises(PredictionNotAvailableError) as error:
        prediction_service.get_prediction("SITE001")

    assert error.value.site_id == "SITE001"


def test_get_prediction_returns_hourly_series_and_peak(prediction_service):
    projection = [
        _prediction(hour=14, consumption_kw=120.0),
        _prediction(hour=18, consumption_kw=190.0),  # le pic
        _prediction(hour=22, consumption_kw=90.0),
    ]
    history = [_history_point(9), _history_point(10)]
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.list_projection_by_site.return_value = projection
    prediction_service.measurement_repository.list_hourly_by_site.return_value = history

    result = prediction_service.get_prediction("SITE001", history_hours=12)

    assert isinstance(result, SitePredictionRead)
    assert [p.predicted_consumption_kw for p in result.points] == [120.0, 190.0, 90.0]
    assert result.prediction.predicted_consumption_kw == 190.0
    assert result.prediction.model_version == "v0.1.0-seed"
    assert result.history == history
    prediction_service.measurement_repository.list_hourly_by_site.assert_called_once_with(
        "SITE001", hours=12
    )


def test_get_prediction_drops_points_before_last_history_hour(prediction_service):
    projection = [
        _prediction(hour=8, consumption_kw=300.0),   # déjà mesuré -> écarté
        _prediction(hour=13, consumption_kw=120.0),  # après -> gardé
        _prediction(hour=19, consumption_kw=180.0),  # après -> gardé
    ]
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.list_projection_by_site.return_value = projection
    prediction_service.measurement_repository.list_hourly_by_site.return_value = [
        _history_point(11)
    ]

    result = prediction_service.get_prediction("SITE001")

    assert [p.predicted_for.hour for p in result.points] == [13, 19]
    assert result.prediction.predicted_consumption_kw == 180.0


def test_get_prediction_keeps_full_series_when_all_points_already_measured(
    prediction_service,
):
    projection = [
        _prediction(hour=8, consumption_kw=100.0),
        _prediction(hour=9, consumption_kw=110.0),
    ]
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.list_projection_by_site.return_value = projection
    prediction_service.measurement_repository.list_hourly_by_site.return_value = [
        _history_point(23)
    ]

    result = prediction_service.get_prediction("SITE001")

    assert len(result.points) == 2
