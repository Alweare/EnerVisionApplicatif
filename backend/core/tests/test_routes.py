from fastapi.testclient import TestClient

import core.security as security_module
from core.security import AuthenticatedUser, get_current_user
from main import app

client = TestClient(app)


def test_me_without_token_returns_401():
    response = client.get("/api/v1/me")

    assert response.status_code == 401


def test_me_with_invalid_token_returns_401(monkeypatch):
    def raise_invalid(token: str):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Token invalide ou expiré.")

    monkeypatch.setattr(security_module, "_decode_token", raise_invalid)

    response = client.get("/api/v1/me", headers={"Authorization": "Bearer garbage"})

    assert response.status_code == 401


def test_me_with_valid_token_returns_user_identity():
    fake_user = AuthenticatedUser(
        sub="user-123", username="jdoe", email="jdoe@example.com", roles=["user"]
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user
    try:
        response = client.get("/api/v1/me", headers={"Authorization": "Bearer whatever"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["sub"] == "user-123"
    assert body["username"] == "jdoe"
    assert body["roles"] == ["user"]
