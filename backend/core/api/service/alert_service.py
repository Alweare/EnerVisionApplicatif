from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.api.repository.alert_repository import AlertRepository
from core.api.repository.site_repository import SiteRepository
from core.api.schemas import AlertRead
from core.api.service.site_service import SiteNotFoundError

__all__ = ["AlertService", "SiteNotFoundError"]


def _as_naive_utc(moment: datetime | None) -> datetime | None:
    if moment is None or moment.tzinfo is None:
        return moment
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


class AlertService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = AlertRepository(db)
        self.site_repository = SiteRepository(db)

    def list_alerts(
        self,
        site_id: str | None = None,
        since: datetime | None = None,
        severities: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AlertRead]:
        """Alertes de la plus récente à la plus ancienne. Chaque critère est
        optionnel : site, date de début, gravités retenues.

        Une liste de gravités vide vaut absence de filtre — le frontend envoie
        alors « toutes », pas « aucune ».
        """
        since = _as_naive_utc(since)
        severities = severities or None

        if site_id is None:
            return self.repository.list_all(
                limit=limit, offset=offset, since=since, severities=severities
            )

        if not self.site_repository.exists(site_id):
            raise SiteNotFoundError(site_id)

        return self.repository.list_by_site(
            site_id, limit=limit, offset=offset, since=since, severities=severities
        )
