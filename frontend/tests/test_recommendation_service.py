from unittest.mock import patch

import pytest

from services.api_client import BackendUnavailableError
from services.recommendation_service import (
    get_my_recommendations,
    refresh_my_recommendations,
    set_recommendation_status,
)


@patch("services.recommendation_service.get")
def test_get_my_recommendations_defaults_to_pending(mock_get):
    payload = [{"site_id": "SITE001", "action_type": "shift_load"}]
    mock_get.return_value = payload

    result = get_my_recommendations()

    mock_get.assert_called_once_with(
        "/api/v1/me/recommendations?status=pending", timeout=10
    )
    assert result == payload


@patch("services.recommendation_service.get")
def test_get_my_recommendations_without_status_filter(mock_get):
    mock_get.return_value = []

    get_my_recommendations(status=None)

    mock_get.assert_called_once_with("/api/v1/me/recommendations", timeout=10)


@patch("services.recommendation_service.get")
def test_get_my_recommendations_with_explicit_status(mock_get):
    mock_get.return_value = []

    get_my_recommendations(status="applied")

    mock_get.assert_called_once_with(
        "/api/v1/me/recommendations?status=applied", timeout=10
    )


@patch("services.recommendation_service.get")
def test_get_my_recommendations_propagates_backend_errors(mock_get):
    mock_get.side_effect = BackendUnavailableError("boom")

    with pytest.raises(BackendUnavailableError):
        get_my_recommendations()


@patch("services.recommendation_service.post")
def test_refresh_my_recommendations_returns_created_count(mock_post):
    mock_post.return_value = {"created": 3}

    result = refresh_my_recommendations()

    mock_post.assert_called_once_with(
        "/api/v1/me/recommendations/refresh", timeout=15
    )
    assert result == 3


@patch("services.recommendation_service.post")
def test_refresh_my_recommendations_defaults_to_zero(mock_post):
    mock_post.return_value = {}

    assert refresh_my_recommendations() == 0


@patch("services.recommendation_service.patch")
def test_set_recommendation_status_patches_the_recommendation(mock_patch):
    updated = {"recommendation_id": "abc", "status": "applied"}
    mock_patch.return_value = updated

    result = set_recommendation_status("abc", "applied")

    mock_patch.assert_called_once_with(
        "/api/v1/recommendations/abc", json={"status": "applied"}, timeout=10
    )
    assert result == updated


@patch("services.recommendation_service.patch")
def test_set_recommendation_status_propagates_backend_errors(mock_patch):
    mock_patch.side_effect = BackendUnavailableError("boom")

    with pytest.raises(BackendUnavailableError):
        set_recommendation_status("abc", "dismissed")
