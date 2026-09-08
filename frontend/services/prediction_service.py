import os

import requests

BACKEND_URL = os.environ["BACKEND_URL"]


def get_site_prediction(site_id: str, history_limit: int = 200) -> dict | None:
    """Prédiction courante d'un site (pic prévu + modèle + historique).

    Renvoie `None` si le site n'existe pas (404) ou si aucune prédiction n'est
    encore disponible (503).
    """
    response = requests.get(
        f"{BACKEND_URL}/api/v1/backend/sites/{site_id}/predictions",
        params={"history_limit": history_limit},
        timeout=10,
    )
    if response.status_code in (404, 503):
        return None
    response.raise_for_status()
    return response.json()
