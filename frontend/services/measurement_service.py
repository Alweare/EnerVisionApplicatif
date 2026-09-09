from services.api_client import get


def get_current_measurement(site_id: str) -> dict | None:
    """Dernière mesure d'un site, ou `None` si aucune mesure n'est enregistrée."""
    return get(
        f"/api/v1/backend/sites/{site_id}/current", timeout=10, allow_404=True
    )


def get_measurement_history(site_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Historique des mesures d'un site (de la plus récente à la plus ancienne)."""
    return get(
        f"/api/v1/backend/sites/{site_id}/measurements",
        params={"limit": limit, "offset": offset},
        timeout=10,
    )
