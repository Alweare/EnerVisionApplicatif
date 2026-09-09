from datetime import datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from core.api.schemas import PredictionRead
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
    return service


def _prediction(site_id: str = "SITE001") -> PredictionRead:
    return PredictionRead(
        prediction_id=uuid4(),
        site_id=site_id,
        predicted_for=datetime(2026, 9, 8, 13, 0, 0),
        predicted_consumption_kw=187.3,
        model_version="v0.1.0-seed",
        created_at=datetime(2026, 9, 8, 11, 0, 0),
    )


# --- get_prediction ------------------------------------------------------

def test_get_prediction_raises_when_site_unknown(prediction_service):
    prediction_service.site_repository.exists.return_value = False

    with pytest.raises(SiteNotFoundError) as error:
        prediction_service.get_prediction("SITE999")

    assert error.value.site_id == "SITE999"
    prediction_service.repository.get_current_by_site.assert_not_called()


def test_get_prediction_raises_when_no_prediction_stored(prediction_service):
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.get_current_by_site.return_value = None

    with pytest.raises(PredictionNotAvailableError) as error:
        prediction_service.get_prediction("SITE001")

    assert error.value.site_id == "SITE001"


def test_get_prediction_returns_current_prediction(prediction_service):
    expected = _prediction()
    prediction_service.site_repository.exists.return_value = True
    prediction_service.repository.get_current_by_site.return_value = expected

    result = prediction_service.get_prediction("SITE001")

    assert result is expected
    assert isinstance(result, PredictionRead)
    prediction_service.repository.get_current_by_site.assert_called_once_with("SITE001")
