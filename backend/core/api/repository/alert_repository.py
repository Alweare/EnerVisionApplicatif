from datetime import datetime

from sqlalchemy.orm import Session

from core.api.models.alert import Alert
from core.api.schemas import AlertRead


class AlertRepository:

    def __init__(self, db: Session):
        self.db = db

    def list_all(
        self,
        limit: int,
        offset: int,
        since: datetime | None = None,
        severities: list[str] | None = None,
    ) -> list[AlertRead]:
        return self._list(
            None, since=since, severities=severities, limit=limit, offset=offset
        )

    def list_by_site(
        self,
        site_id: str,
        limit: int,
        offset: int,
        since: datetime | None = None,
        severities: list[str] | None = None,
    ) -> list[AlertRead]:
        return self._list(
            site_id, since=since, severities=severities, limit=limit, offset=offset
        )

    def _list(
        self,
        site_id: str | None,
        since: datetime | None,
        severities: list[str] | None,
        limit: int,
        offset: int,
    ) -> list[AlertRead]:
        query = self.db.query(Alert)
        if site_id is not None:
            query = query.filter(Alert.site_id == site_id)
        if since is not None:
            query = query.filter(Alert.created_at >= since)
        if severities:
            query = query.filter(Alert.severity.in_(severities))

        rows = (
            query.order_by(Alert.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
        return [AlertRead.model_validate(row) for row in rows]
