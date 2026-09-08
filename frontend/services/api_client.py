import os

import requests
import streamlit as st

from authentification.auth import get_access_token

CORE_URL = os.environ.get("CORE_URL", "http://localhost:8000")


class BackendUnavailableError(Exception):
    """Le backend core est injoignable ou a répondu par une erreur inattendue."""

def get(path: str, timeout: float = 5.0) -> dict:
    """Appelle GET {CORE_URL}{path} avec le token de l'utilisateur connecté."""
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        response = requests.get(f"{CORE_URL}{path}", headers=headers, timeout=timeout)
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
