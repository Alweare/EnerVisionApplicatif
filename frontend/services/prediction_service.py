import os

import requests

CORE_URL = os.environ["CORE_URL"]


def get_site_prediction(site_id: str, history_hours: int = 24) -> dict | None:
    """Prédiction courante d'un site : projection horaire + pic prévu + modèle
    + historique agrégé à l'heure sur `history_hours`.

    Renvoie `None` si le site n'existe pas (404) ou si aucune prédiction n'est
    encore disponible (503).
    """
    response = requests.get(
        f"{CORE_URL}/api/v1/backend/sites/{site_id}/predictions",
        params={"history_hours": history_hours},
        timeout=10,
    )
    if response.status_code in (404, 503):
        return None
    response.raise_for_status()
    return response.json()
