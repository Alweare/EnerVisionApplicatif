from datetime import datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from core.api.schemas import RecommendationRead
from core.api.service.recommendation_service import RecommendationNotFoundError
from core.main import app
from core.security import AuthenticatedUser, get_current_user
from shared.database import get_db

client = TestClient(app)

_USER_ID = "7e57c0de-0000-4000-8000-000000000001"


@pytest.fixture(autouse=True)
def _overrides():
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        sub=_USER_ID, username="test"
    )
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def recommendation_service(monkeypatch):
    fake = Mock()
    monkeypatch.setattr(
        "core.api.controller.recommendation.RecommendationService", lambda db: fake
    )
    return fake


def _reco(status: str = "pending") -> RecommendationRead:
    return RecommendationRead(
        recommendation_id=uuid4(),
        site_id="SITE001",
        prediction_id=uuid4(),
        rule_key="peak_over_capacity",
        action_type="reduce_load",
        message="Dépassement de capacité prévu à 18h00.",
        status=status,
        created_at=datetime(2026, 9, 8, 14, 0),
    )


def test_list_my_recommendations_returns_service_result(recommendation_service):
    recommendation_service.list_for_user.return_value = [_reco(), _reco("applied")]

    response = client.get("/api/v1/me/recommendations")

    assert response.status_code == 200
    assert len(response.json()) == 2
    recommendation_service.list_for_user.assert_called_once_with(UUID(_USER_ID), None)


def test_list_my_recommendations_forwards_status_filter(recommendation_service):
    recommendation_service.list_for_user.return_value = []

    client.get("/api/v1/me/recommendations?status=pending")

    recommendation_service.list_for_user.assert_called_once_with(UUID(_USER_ID), "pending")


def test_list_my_recommendations_rejects_unknown_status(recommendation_service):
    response = client.get("/api/v1/me/recommendations?status=whatever")

    assert response.status_code == 422


def test_refresh_returns_created_count(recommendation_service):
    recommendation_service.generate_for_user.return_value = 4

    response = client.post("/api/v1/me/recommendations/refresh")

    assert response.status_code == 200
    assert response.json() == {"created": 4}
    recommendation_service.generate_for_user.assert_called_once_with(UUID(_USER_ID))


def test_patch_status_returns_updated(recommendation_service):
    recommendation_service.set_status.return_value = _reco("applied")
    reco_id = uuid4()

    response = client.patch(f"/api/v1/recommendations/{reco_id}", json={"status": "applied"})

    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    recommendation_service.set_status.assert_called_once_with(reco_id, "applied")


def test_patch_status_404_when_unknown(recommendation_service):
    reco_id = uuid4()
    recommendation_service.set_status.side_effect = RecommendationNotFoundError(reco_id)

    response = client.patch(f"/api/v1/recommendations/{reco_id}", json={"status": "applied"})

    assert response.status_code == 404


def test_patch_status_422_on_bad_status(recommendation_service):
    response = client.patch(
        f"/api/v1/recommendations/{uuid4()}", json={"status": "nope"}
    )

    assert response.status_code == 422


def test_recommendations_require_authentication():
    app.dependency_overrides.pop(get_current_user, None)

    response = client.get("/api/v1/me/recommendations")

    assert response.status_code == 401
