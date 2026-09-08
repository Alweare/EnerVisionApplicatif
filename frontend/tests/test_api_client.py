from unittest.mock import MagicMock

import pytest
import requests

from services import api_client


def _response(status_code, json_data=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_data or {}
    return response


def test_get_attaches_bearer_token_and_returns_json(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok-123")
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return _response(200, {"ok": True})

    monkeypatch.setattr(api_client.requests, "get", fake_get)

    result = api_client.get("/api/v1/me")

    assert result == {"ok": True}
    assert captured["headers"] == {"Authorization": "Bearer tok-123"}
    assert captured["url"] == f"{api_client.CORE_URL}/api/v1/me"


def test_get_without_token_sends_no_authorization_header(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: None)
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["headers"] = headers
        return _response(200, {})

    monkeypatch.setattr(api_client.requests, "get", fake_get)

    api_client.get("/api/v1/me")

    assert captured["headers"] == {}


def test_get_raises_backend_unavailable_on_connection_error(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok")

    def fake_get(*args, **kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(api_client.requests, "get", fake_get)

    with pytest.raises(api_client.BackendUnavailableError):
        api_client.get("/api/v1/me")


def test_get_raises_backend_unavailable_on_server_error(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok")
    monkeypatch.setattr(api_client.requests, "get", lambda *a, **k: _response(500))

    with pytest.raises(api_client.BackendUnavailableError):
        api_client.get("/api/v1/me")


def test_get_returns_none_on_404_when_allow_404(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok")
    monkeypatch.setattr(api_client.requests, "get", lambda *a, **k: _response(404))

    assert api_client.get("/api/v1/backend/sites/X/current", allow_404=True) is None


def test_get_still_raises_on_404_by_default(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok")
    monkeypatch.setattr(api_client.requests, "get", lambda *a, **k: _response(404))

    with pytest.raises(api_client.BackendUnavailableError):
        api_client.get("/api/v1/backend/sites/X/current")


def test_post_sends_json_body_with_bearer_token(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok-123")
    captured = {}

    def fake_post(url, params=None, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _response(200, {"created": 2})

    monkeypatch.setattr(api_client.requests, "post", fake_post)

    result = api_client.post("/api/v1/me/recommendations/refresh", json={"a": 1})

    assert result == {"created": 2}
    assert captured["json"] == {"a": 1}
    assert captured["headers"] == {"Authorization": "Bearer tok-123"}
    assert captured["url"] == f"{api_client.CORE_URL}/api/v1/me/recommendations/refresh"


def test_post_without_json_omits_body(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok")
    captured = {}

    def fake_post(url, params=None, headers=None, timeout=None):
        captured["called"] = True
        return _response(200, {})

    monkeypatch.setattr(api_client.requests, "post", fake_post)

    api_client.post("/api/v1/me/recommendations/refresh")

    assert captured["called"]


def test_post_raises_backend_unavailable_on_server_error(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok")
    monkeypatch.setattr(api_client.requests, "post", lambda *a, **k: _response(500))

    with pytest.raises(api_client.BackendUnavailableError):
        api_client.post("/api/v1/me/recommendations/refresh")


def test_patch_sends_json_body_with_bearer_token(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok-123")
    captured = {}

    def fake_patch(url, params=None, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _response(200, {"status": "applied"})

    monkeypatch.setattr(api_client.requests, "patch", fake_patch)

    result = api_client.patch("/api/v1/recommendations/abc", json={"status": "applied"})

    assert result == {"status": "applied"}
    assert captured["json"] == {"status": "applied"}
    assert captured["headers"] == {"Authorization": "Bearer tok-123"}
    assert captured["url"] == f"{api_client.CORE_URL}/api/v1/recommendations/abc"


def test_patch_raises_backend_unavailable_on_server_error(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "tok")
    monkeypatch.setattr(api_client.requests, "patch", lambda *a, **k: _response(500))

    with pytest.raises(api_client.BackendUnavailableError):
        api_client.patch("/api/v1/recommendations/abc", json={"status": "applied"})


def test_get_forces_relogin_on_401(monkeypatch):
    monkeypatch.setattr(api_client, "get_access_token", lambda: "expired-token")
    monkeypatch.setattr(api_client.requests, "get", lambda *a, **k: _response(401))

    st_mock = MagicMock()
    st_mock.stop.side_effect = SystemExit
    monkeypatch.setattr(api_client, "st", st_mock)

    with pytest.raises(SystemExit):
        api_client.get("/api/v1/me")

    st_mock.logout.assert_called_once()
