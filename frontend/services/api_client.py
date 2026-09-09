import os

import requests
import streamlit as st

from authentification.auth import get_access_token

CORE_URL = os.environ.get("CORE_URL")


class BackendUnavailableError(Exception):
    """Le backend core est injoignable ou a répondu par une erreur inattendue."""


def _request(method: str, path: str, *, params: dict | None = None,
             json: dict | None = None, timeout: float = 5.0,
             allow_404: bool = False) -> dict | list | None:
    """Appelle {method} {CORE_URL}{path} avec le token de l'utilisateur connecté.

    `allow_404` : renvoie `None` sur un 404 au lieu de lever, pour les
    endpoints où « pas trouvé » est un cas nominal (ex. aucune mesure encore
    enregistrée pour un site).
    """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    kwargs = {"params": params, "headers": headers, "timeout": timeout}
    if json is not None:
        kwargs["json"] = json

    try:
        response = getattr(requests, method)(f"{CORE_URL}{path}", **kwargs)
    except requests.RequestException as error:
        raise BackendUnavailableError("Le service backend est indisponible.") from error

    if response.status_code == 401:
        st.warning("Votre session a expiré. Merci de vous reconnecter.")
        st.logout()
        st.stop()

    if response.status_code == 404 and allow_404:
        return None

    if response.status_code >= 400:
        raise BackendUnavailableError(
            f"Le backend a répondu avec une erreur ({response.status_code})."
        )

    return response.json()


def get(path: str, params: dict | None = None, timeout: float = 5.0,
        allow_404: bool = False) -> dict | list | None:
    """Appelle GET {CORE_URL}{path} avec le token de l'utilisateur connecté."""
    return _request("get", path, params=params, timeout=timeout, allow_404=allow_404)


def post(path: str, json: dict | None = None, timeout: float = 5.0) -> dict:
    """Appelle POST {CORE_URL}{path} avec le token de l'utilisateur connecté."""
    return _request("post", path, json=json, timeout=timeout)


def patch(path: str, json: dict | None = None, timeout: float = 5.0) -> dict:
    """Appelle PATCH {CORE_URL}{path} avec le token de l'utilisateur connecté."""
    return _request("patch", path, json=json, timeout=timeout)
