from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from core.api.schemas import (
    ModelInfo,
    MeasurementRead,
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
    service.model_repository = Mock()
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


def _measurement(
    site_id: str = "SITE001", date: datetime | None = None
) -> MeasurementRead:
    return MeasurementRead(
        measurement_id=uuid4(),
        site_id=site_id,
        measurement_date=date or datetime(2026, 9, 8, 9, 0, 0),
        consumption_kw=104.47,
        consumption_kwh=104.47,
        voltage_v=402.6,
        current_a=163.9,
        power_factor=0.914,
        temperature_celsius=None,
        humidity_percent=61.0,
        null_reason=None,
        data_quality="good",
        created_at=datetime(2026, 9, 8, 9, 0, 1),
    )


def _model():
    return ModelInfo(
        model_version="v0.1.0-seed",
        algorithm="régression linéaire (scikit-learn)",
        trained_at=datetime(2026, 8, 28, 9, 0, 0),
        mae=8.42,
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
    history = [_measurement(), _measurement()]
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.list_projection_by_site.return_value = projection
    prediction_service.model_repository.get_by_version.return_value = _model()
    prediction_service.measurement_repository.list_by_site.return_value = history

    result = prediction_service.get_prediction("SITE001", history_limit=50)

    assert isinstance(result, SitePredictionRead)
    assert [p.predicted_consumption_kw for p in result.points] == [120.0, 190.0, 90.0]
    assert result.prediction.predicted_consumption_kw == 190.0
    assert result.prediction.predicted_for == datetime(2026, 9, 8, 18, 0, 0)
    assert result.model.algorithm == "régression linéaire (scikit-learn)"
    assert result.history == history
    prediction_service.model_repository.get_by_version.assert_called_once_with(
        "v0.1.0-seed"
    )
    prediction_service.measurement_repository.list_by_site.assert_called_once_with(
        "SITE001", limit=50, offset=0
    )


def test_get_prediction_tolerates_missing_model(prediction_service):
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.list_projection_by_site.return_value = [
        _prediction(model_version=None)
    ]
    prediction_service.measurement_repository.list_by_site.return_value = []

    result = prediction_service.get_prediction("SITE001")

    assert result.model is None
    prediction_service.model_repository.get_by_version.assert_not_called()


def test_get_prediction_drops_points_before_last_measurement(prediction_service):
    projection = [
        _prediction(hour=8, consumption_kw=300.0),   # déjà mesuré -> écarté
        _prediction(hour=13, consumption_kw=120.0),  # après la mesure -> gardé
        _prediction(hour=19, consumption_kw=180.0),  # après la mesure -> gardé
    ]
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.list_projection_by_site.return_value = projection
    prediction_service.model_repository.get_by_version.return_value = None
    prediction_service.measurement_repository.list_by_site.return_value = [
        _measurement(date=datetime(2026, 9, 8, 11, 0, 0))
    ]

    result = prediction_service.get_prediction("SITE001")

    assert [p.predicted_for.hour for p in result.points] == [13, 19]
    # le pic (300 kW à 8h) est passé : il ne doit pas être retenu
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
    prediction_service.model_repository.get_by_version.return_value = None
    prediction_service.measurement_repository.list_by_site.return_value = [
        _measurement(date=datetime(2026, 9, 8, 23, 0, 0))
    ]

    result = prediction_service.get_prediction("SITE001")

    assert len(result.points) == 2
