from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from core.api.service.recommendation_service import (
    RecommendationNotFoundError,
    RecommendationService,
)


@pytest.fixture
def service():
    svc = RecommendationService.__new__(RecommendationService)
    svc.repository = Mock()
    svc.prediction_repository = Mock()
    return svc


def _prediction(prediction_id, site_id="SITE001", kw=190.0):
    return SimpleNamespace(
        prediction_id=prediction_id,
        site_id=site_id,
        predicted_consumption_kw=kw,
        predicted_for=datetime(2026, 9, 8, 18, 0),
    )


def _site(capacity_kw=200.0):
    return SimpleNamespace(capacity_kw=capacity_kw)


# --- generate_for_user ---------------------------------------------------

def test_generate_inserts_one_reco_per_matching_rule(service):
    pid = uuid4()
    service.prediction_repository.list_upcoming_for_user.return_value = [
        (_prediction(pid, kw=190.0), _site(200.0)),  # -> shift_load
    ]
    service.repository.existing_keys_for_predictions.return_value = set()
    service.repository.add_all.return_value = 1

    created = service.generate_for_user(uuid4())

    assert created == 1
    rows = service.repository.add_all.call_args[0][0]
    assert len(rows) == 1
    assert rows[0]["rule_key"] == "peak_over_90pct_capacity"
    assert rows[0]["action_type"] == "shift_load"
    assert rows[0]["site_id"] == "SITE001"
    assert rows[0]["status"] == "pending"
    assert rows[0]["predicted_for"] == datetime(2026, 9, 8, 18, 0)


def test_generate_skips_already_emitted_pairs(service):
    pid = uuid4()
    service.prediction_repository.list_upcoming_for_user.return_value = [
        (_prediction(pid, kw=190.0), _site(200.0)),
    ]
    service.repository.existing_keys_for_predictions.return_value = {
        (pid, "peak_over_90pct_capacity")
    }

    service.generate_for_user(uuid4())

    service.repository.add_all.assert_called_once_with([])


def test_generate_ignores_predictions_without_peak(service):
    service.prediction_repository.list_upcoming_for_user.return_value = [
        (_prediction(uuid4(), kw=100.0), _site(200.0)),  # 50 % -> aucune règle
    ]
    service.repository.existing_keys_for_predictions.return_value = set()

    service.generate_for_user(uuid4())

    service.repository.add_all.assert_called_once_with([])


# --- set_status --------------------------------------------------------

def test_set_status_returns_updated_recommendation(service):
    updated = object()
    service.repository.update_status.return_value = updated

    assert service.set_status(uuid4(), "applied") is updated


def test_set_status_raises_when_missing(service):
    service.repository.update_status.return_value = None
    recommendation_id = uuid4()

    with pytest.raises(RecommendationNotFoundError):
        service.set_status(recommendation_id, "applied")


# --- list_for_user ----------------------------------------------------

def test_list_for_user_delegates_to_repository(service):
    service.repository.list_for_user.return_value = ["r1", "r2"]
    user_id = uuid4()

    assert service.list_for_user(user_id, "pending") == ["r1", "r2"]
    service.repository.list_for_user.assert_called_once_with(user_id, "pending")
