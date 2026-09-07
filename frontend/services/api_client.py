"""Client HTTP centralisé pour les appels du frontend vers backend/core.

Attache automatiquement l'access token Keycloak de l'utilisateur connecté et
gère proprement les cas d'erreur (backend injoignable, session expirée).
"""

import os

import requests
import streamlit as st

from authentification.auth import get_access_token

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


class BackendUnavailableError(Exception):
    """Le backend core est injoignable ou a répondu par une erreur inattendue."""


def get(path: str, timeout: float = 5.0) -> dict:
    """Appelle GET {BACKEND_URL}{path} avec le token de l'utilisateur connecté."""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        response = requests.get(f"{BACKEND_URL}{path}", headers=headers, timeout=timeout)
    except requests.RequestException as error:
        raise BackendUnavailableError("Le service backend est indisponible.") from error

    if response.status_code == 401:
        st.warning("Votre session a expiré. Merci de vous reconnecter.")
        st.logout()
        st.stop()

    if response.status_code >= 400:
        raise BackendUnavailableError(
            f"Le backend a répondu avec une erreur ({response.status_code})."
        )

    return response.json()
