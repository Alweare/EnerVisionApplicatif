import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core import security

_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_PUBLIC_PEM = _PRIVATE_KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)

ISSUER = "http://keycloak:8080/realms/enervision"
AUDIENCE = "test-client"


class _FakeSigningKey:
    key = _PUBLIC_PEM


class _FakeJwksClient:
    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey()


@pytest.fixture
def mock_oidc(monkeypatch):
    """Mocke la découverte OIDC et le client JWKS : aucun appel réseau à Keycloak."""
    monkeypatch.setattr(
        security,
        "_get_oidc_config",
        lambda: security._OidcConfig(
            issuer=ISSUER, jwks_uri=f"{ISSUER}/protocol/openid-connect/certs"
        ),
    )
    monkeypatch.setattr(security, "_get_jwks_client", lambda: _FakeJwksClient())
    monkeypatch.setattr(security.settings, "keycloak_client_id", AUDIENCE)


def _make_token(**overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": "user-123",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
        "preferred_username": "jdoe",
        "email": "jdoe@example.com",
        "realm_access": {"roles": ["user"]},
    }
    claims.update(overrides)
    return jwt.encode(claims, _PRIVATE_KEY, algorithm="RS256")


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_valid_token_returns_authenticated_user(mock_oidc):
    user = security.get_current_user(_credentials(_make_token()))

    assert user.sub == "user-123"
    assert user.username == "jdoe"
    assert user.email == "jdoe@example.com"
    assert user.roles == ["user"]


def test_missing_optional_claims_does_not_crash(mock_oidc):
    minimal_token = jwt.encode(
        {
            "sub": "user-123",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
        },
        _PRIVATE_KEY,
        algorithm="RS256",
    )

    user = security.get_current_user(_credentials(minimal_token))

    assert user.sub == "user-123"
    assert user.username is None
    assert user.email is None
    assert user.roles == []


def test_missing_credentials_raises_401(mock_oidc):
    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(None)

    assert exc_info.value.status_code == 401


def test_malformed_token_raises_401(mock_oidc):
    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(_credentials("not-a-jwt"))

    assert exc_info.value.status_code == 401


def test_expired_token_raises_401(mock_oidc):
    now = int(time.time())
    token = _make_token(iat=now - 600, exp=now - 300)

    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(_credentials(token))

    assert exc_info.value.status_code == 401


def test_wrong_audience_raises_401(mock_oidc):
    token = _make_token(aud="another-client")

    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(_credentials(token))

    assert exc_info.value.status_code == 401


def test_wrong_issuer_raises_401(mock_oidc):
    token = _make_token(iss="http://attacker.example/realms/fake")

    with pytest.raises(HTTPException) as exc_info:
        security.get_current_user(_credentials(token))

    assert exc_info.value.status_code == 401


def test_oidc_discovery_unreachable_raises_503(monkeypatch):
    security._get_oidc_config.cache_clear()

    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(security.httpx, "get", fake_get)

    with pytest.raises(HTTPException) as exc_info:
        security._get_oidc_config()

    assert exc_info.value.status_code == 503
    security._get_oidc_config.cache_clear()
