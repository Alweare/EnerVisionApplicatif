"""Validation des access tokens JWT émis par Keycloak.

La validation est locale : les clés publiques (JWKS) et les endpoints du
realm sont récupérés une seule fois via la découverte OpenID Connect, puis
mis en cache. Keycloak n'est donc pas recontacté à chaque requête.
"""

from functools import lru_cache

import httpx
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from core.config import settings

_bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser(BaseModel):
    """Identité extraite d'un access token Keycloak valide."""

    sub: str
    username: str | None = None
    email: str | None = None
    roles: list[str] = []


class _OidcConfig(BaseModel):
    issuer: str
    jwks_uri: str


@lru_cache
def _get_oidc_config() -> _OidcConfig:
    """Récupère la configuration OIDC du realm via la découverte standard.

    Mise en cache pour la durée de vie du process : évite un aller-retour
    réseau vers Keycloak à chaque validation de token.
    """
    discovery_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}"
        "/.well-known/openid-configuration"
    )
    try:
        response = httpx.get(discovery_url, timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service d'authentification indisponible.",
        ) from error

    data = response.json()
    return _OidcConfig(issuer=data["issuer"], jwks_uri=data["jwks_uri"])


@lru_cache
def _get_jwks_client() -> jwt.PyJWKClient:
    """Client JWKS avec cache des clés publiques (rafraîchi automatiquement par PyJWT)."""
    oidc_config = _get_oidc_config()
    return jwt.PyJWKClient(oidc_config.jwks_uri, cache_keys=True)


def _decode_token(token: str) -> dict:
    oidc_config = _get_oidc_config()
    jwks_client = _get_jwks_client()

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.keycloak_client_id,
            issuer=oidc_config.issuer,
        )
    except jwt.PyJWTError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    """Dépendance FastAPI : authentifie la requête via son access token Keycloak."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = _decode_token(credentials.credentials)

    return AuthenticatedUser(
        sub=claims["sub"],
        username=claims.get("preferred_username"),
        email=claims.get("email"),
        roles=claims.get("realm_access", {}).get("roles", []),
    )
