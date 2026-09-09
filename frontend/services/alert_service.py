from datetime import datetime

from services.api_client import get


def get_alerts(
    site_id: str | None = None,
    since: datetime | None = None,
    severities: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Alertes de la plus récente à la plus ancienne. Chaque critère est
    optionnel : site, date de début, gravités retenues. Une liste de gravités
    vide n'est pas envoyée — l'API la lirait comme « toutes »."""
    params: dict = {"limit": limit, "offset": offset}
    if site_id is not None:
        params["site_id"] = site_id
    if since is not None:
        params["since"] = since.isoformat()
    if severities:
        params["severity"] = severities

    return get("/api/v1/backend/alerts", params=params, timeout=10)
