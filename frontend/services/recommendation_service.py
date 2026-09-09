from services.api_client import get, patch, post


def get_my_recommendations(status: str | None = "pending") -> list[dict]:
    """Recommandations des sites de l'utilisateur connecté (par défaut : à traiter).

    `status` filtre sur `pending`, `applied` ou `dismissed` ; `None` renvoie tout.
    """
    path = "/api/v1/me/recommendations"
    if status:
        path = f"{path}?status={status}"
    return get(path, timeout=10)


def refresh_my_recommendations() -> int:
    """Recalcule les recommandations de l'utilisateur connecté. Retourne le nb créé."""
    result = post("/api/v1/me/recommendations/refresh", timeout=15)
    return result.get("created", 0)


def set_recommendation_status(recommendation_id: str, status: str) -> dict:
    """Change le statut d'une reco (`pending`, `applied`, `dismissed`).

    Retourne la recommandation mise à jour.
    """
    return patch(
        f"/api/v1/recommendations/{recommendation_id}",
        json={"status": status},
        timeout=10,
    )
