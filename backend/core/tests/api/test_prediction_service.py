from datetime import datetime
from unittest.mock import Mock

import pytest

from core.api.schemas import PredictionRead
from core.api.service import model_registry
from core.api.service.model_registry import ConsumptionForecast, load_consumption_model
from core.api.service.prediction_service import (
    ModelNotAvailableError,
    PredictionService,
    SiteNotFoundError,
)


@pytest.fixture
def prediction_service():
    service = PredictionService.__new__(PredictionService)
    service.site_repository = Mock()
    service._load_model = Mock(return_value=None)
    return service


def _model(name: str = "consumption-predictor", version: str | None = "3") -> Mock:
    model = Mock()
    model.name = name
    model.version = version
    model.predict_next.return_value = ConsumptionForecast(
        predicted_consumption_kw=187.3,
        prediction_date=datetime(2026, 9, 8, 13, 0, 0),
    )
    return model


# --- get_prediction --------------------------------------------------------

def test_get_prediction_raises_when_site_unknown(prediction_service):
    prediction_service.site_repository.exists.return_value = False

    with pytest.raises(SiteNotFoundError) as error:
        prediction_service.get_prediction("SITE999")

    assert error.value.site_id == "SITE999"
    prediction_service._load_model.assert_not_called()


def test_get_prediction_raises_when_no_model_available(prediction_service):
    prediction_service.site_repository.exists.return_value = True
    prediction_service._load_model.return_value = None

    with pytest.raises(ModelNotAvailableError):
        prediction_service.get_prediction("SITE001")


def test_get_prediction_returns_forecast_from_model(prediction_service):
    prediction_service.site_repository.exists.return_value = True
    model = _model()
    prediction_service._load_model.return_value = model

    result = prediction_service.get_prediction("SITE001")

    assert isinstance(result, PredictionRead)
    assert result.site_id == "SITE001"
    assert result.predicted_consumption_kw == 187.3
    assert result.prediction_date == datetime(2026, 9, 8, 13, 0, 0)
    assert result.model_name == "consumption-predictor"
    assert result.model_version == "3"
    assert result.generated_at is not None
    model.predict_next.assert_called_once_with("SITE001")


def test_service_uses_registry_loader_by_default():
    service = PredictionService(db=None)

    assert service._load_model is model_registry.load_consumption_model


# --- model_registry ------------------------------------------------------

def test_load_consumption_model_returns_none_until_a_model_is_published():
    assert load_consumption_model() is None
